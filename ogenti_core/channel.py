"""
channel.py — Communication Channel Abstraction

The channel sits between encoder and decoder, simulating the
"wire" that agents communicate over.  It handles:

  1. Message routing (point-to-point, broadcast, relay chains)
  2. Budget enforcement (reject messages that exceed token budget)
  3. Noise injection (for robustness training)
  4. Logging & metric collection

During MARL training the channel is the environment's message bus.
During inference it's a lightweight router.

Architecture
------------
  Encoder A ──▶ Channel ──▶ Decoder B
                  │
                  ├─ budget check
                  ├─ noise injection (training only)
                  ├─ latency simulation (optional)
                  └─ metric logging
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from ogenti_core.protocol import (
    ProtocolMessage,
    ProtocolConfig,
    MessageType,
    inject_noise,
    compute_compression_ratio,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Channel Statistics
# ─────────────────────────────────────────────────────────────────

@dataclass
class ChannelStats:
    """Accumulated statistics for a communication channel."""

    messages_sent: int = 0
    messages_dropped: int = 0          # budget exceeded
    total_tokens_transmitted: int = 0
    total_original_tokens: int = 0     # NL equivalent
    noise_injections: int = 0
    relay_hops: int = 0

    # Per-sender stats
    per_sender: dict = field(default_factory=lambda: defaultdict(int))
    # Per-type stats
    per_type: dict = field(default_factory=lambda: defaultdict(int))

    @property
    def compression_ratio(self) -> float:
        if self.total_tokens_transmitted == 0:
            return 0.0
        return self.total_original_tokens / self.total_tokens_transmitted

    @property
    def drop_rate(self) -> float:
        total = self.messages_sent + self.messages_dropped
        if total == 0:
            return 0.0
        return self.messages_dropped / total

    def summary(self) -> dict:
        return {
            "messages_sent": self.messages_sent,
            "messages_dropped": self.messages_dropped,
            "drop_rate": f"{self.drop_rate:.2%}",
            "total_tokens": self.total_tokens_transmitted,
            "compression_ratio": f"{self.compression_ratio:.1f}x",
            "noise_injections": self.noise_injections,
            "relay_hops": self.relay_hops,
        }


# ─────────────────────────────────────────────────────────────────
#  Message Callback Type
# ─────────────────────────────────────────────────────────────────

MessageCallback = Callable[[ProtocolMessage], None]


# ─────────────────────────────────────────────────────────────────
#  Communication Channel
# ─────────────────────────────────────────────────────────────────

class CommunicationChannel:
    """
    Central message bus for agent-to-agent protocol communication.

    Usage
    -----
    >>> channel = CommunicationChannel(protocol_config)
    >>> channel.register("agent_0", on_message_callback)
    >>> channel.send(message)  # routes to receiver
    """

    def __init__(
        self,
        protocol_config: Optional[ProtocolConfig] = None,
        inject_noise_prob: float = 0.0,
        episode: int = 0,
    ):
        self.config = protocol_config or ProtocolConfig()
        self.inject_noise_prob = inject_noise_prob
        self.episode = episode
        self.stats = ChannelStats()

        # Registered agent callbacks: agent_id → callback
        self._subscribers: dict[str, MessageCallback] = {}

        # Message history (for replay / analysis)
        self._history: list[ProtocolMessage] = []

        # Intercept hooks (for reward computation, logging, etc.)
        self._hooks: list[Callable[[ProtocolMessage], ProtocolMessage | None]] = []

    # ── Agent Registration ──

    def register(self, agent_id: str, callback: MessageCallback) -> None:
        """Register an agent to receive messages."""
        self._subscribers[agent_id] = callback
        logger.debug("Agent %s registered on channel", agent_id)

    def unregister(self, agent_id: str) -> None:
        """Remove an agent from the channel."""
        self._subscribers.pop(agent_id, None)

    # ── Message Sending ──

    def send(
        self,
        message: ProtocolMessage,
        original_nl_tokens: int = 0,
    ) -> bool:
        """
        Send a message through the channel.

        Parameters
        ----------
        message : ProtocolMessage
            The protocol message to transmit.
        original_nl_tokens : int
            Token count of the original NL (for compression stats).

        Returns
        -------
        bool
            True if message was delivered, False if dropped.
        """
        # 1. Budget check
        budget = self.config.effective_budget(self.episode)
        if message.token_count > budget:
            self.stats.messages_dropped += 1
            logger.warning(
                "Message from %s dropped: %d tokens > budget %d",
                message.sender_id, message.token_count, budget,
            )
            return False

        # 2. Apply intercept hooks
        for hook in self._hooks:
            result = hook(message)
            if result is None:
                # Hook rejected message
                self.stats.messages_dropped += 1
                return False
            message = result

        # 3. Noise injection (training only)
        if self.inject_noise_prob > 0:
            noised = inject_noise(
                message,
                error_rate=self.inject_noise_prob,
                vocab_size=self.config.vocab_size,
            )
            if noised.token_ids != message.token_ids:
                self.stats.noise_injections += 1
            message = noised

        # 4. Record stats
        self.stats.messages_sent += 1
        self.stats.total_tokens_transmitted += message.token_count
        self.stats.total_original_tokens += original_nl_tokens
        self.stats.per_sender[message.sender_id] += 1
        self.stats.per_type[message.message_type.value if message.message_type else "unknown"] += 1

        if message.is_relay:
            self.stats.relay_hops += len(message.route_chain)

        # 5. Record history
        self._history.append(message)

        # 6. Route to receiver(s)
        self._deliver(message)

        return True

    def broadcast(
        self,
        message: ProtocolMessage,
        exclude: Optional[set[str]] = None,
        original_nl_tokens: int = 0,
    ) -> int:
        """
        Broadcast a message to all registered agents.

        Returns the number of successful deliveries.
        """
        exclude = exclude or set()
        delivered = 0

        for agent_id in self._subscribers:
            if agent_id in exclude or agent_id == message.sender_id:
                continue

            routed = ProtocolMessage(
                token_ids=message.token_ids,
                message_type=message.message_type,
                sender_id=message.sender_id,
                receiver_id=agent_id,
                route_chain=message.route_chain,
                metadata=message.metadata,
            )
            if self.send(routed, original_nl_tokens=original_nl_tokens):
                delivered += 1

        return delivered

    # ── Relay ──

    def relay(
        self,
        message: ProtocolMessage,
        via: str,
        final_receiver: str,
    ) -> bool:
        """
        Route a message through an intermediary agent.

        The intermediary may compress/transform the message further
        before forwarding.
        """
        route = list(message.route_chain) + [via]
        hop1 = ProtocolMessage(
            token_ids=message.token_ids,
            message_type=MessageType.RELAY,
            sender_id=message.sender_id,
            receiver_id=via,
            route_chain=route,
            metadata={
                **message.metadata,
                "final_receiver": final_receiver,
            },
        )
        return self.send(hop1)

    # ── Hooks ──

    def add_hook(
        self,
        hook: Callable[[ProtocolMessage], ProtocolMessage | None],
    ) -> None:
        """
        Add an intercept hook. Hooks are called in order before
        delivery. Return None to drop the message.
        """
        self._hooks.append(hook)

    # ── Episode Management ──

    def set_episode(self, episode: int) -> None:
        """Update the current episode (affects budget decay)."""
        self.episode = episode

    def reset(self) -> None:
        """Reset channel state for a new episode."""
        self._history.clear()
        self.stats = ChannelStats()

    def reset_stats_only(self) -> None:
        """Reset stats but keep history."""
        self.stats = ChannelStats()

    # ── History & Analysis ──

    @property
    def history(self) -> list[ProtocolMessage]:
        """Read-only access to message history."""
        return list(self._history)

    def get_conversation(
        self,
        agent_a: str,
        agent_b: str,
    ) -> list[ProtocolMessage]:
        """Get all messages between two specific agents."""
        return [
            m for m in self._history
            if (m.sender_id == agent_a and m.receiver_id == agent_b)
            or (m.sender_id == agent_b and m.receiver_id == agent_a)
        ]

    def compute_avg_compression(self) -> float:
        """Compute average compression ratio across all messages."""
        if not self._history:
            return 0.0
        return self.stats.compression_ratio

    # ── Internal ──

    def _deliver(self, message: ProtocolMessage) -> None:
        """Route message to the appropriate subscriber."""
        receiver = message.receiver_id

        if receiver is None:
            # Broadcast to all (excluding sender)
            for aid, cb in self._subscribers.items():
                if aid != message.sender_id:
                    cb(message)
            return

        if receiver in self._subscribers:
            self._subscribers[receiver](message)
        else:
            logger.warning(
                "No subscriber for receiver %s (sender: %s)",
                receiver, message.sender_id,
            )

    # ── String ──

    def __repr__(self) -> str:
        return (
            f"CommunicationChannel("
            f"agents={len(self._subscribers)}, "
            f"episode={self.episode}, "
            f"budget={self.config.effective_budget(self.episode)}, "
            f"history={len(self._history)})"
        )
