"""
protocol.py — Ogenti Protocol Definition

Defines the structure of protocol messages that agents exchange
during training and inference. Messages are sequences of token IDs
from the base model's existing vocabulary, re-purposed for
compressed inter-agent communication.

Key Design Choice: We re-use existing tokenizer vocabulary rather
than creating new tokens. The LoRA adapters learn to re-map the
embedding space so that existing tokens carry protocol-specific
meanings. This lets us leverage pre-trained embeddings as a
warm start.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Optional


# ─────────────────────────────────────────────────────────────────
#  Message Types — high-level intent categories
# ─────────────────────────────────────────────────────────────────

class MessageType(Enum):
    """Top-level intent of the protocol message."""
    INSTRUCT = auto()    # sender tells receiver to perform a task
    REPORT = auto()      # sender delivers results back
    NEGOTIATE = auto()   # bidirectional task coordination
    RELAY = auto()       # forwarding to another agent
    ACK = auto()         # simple acknowledgement
    ERROR = auto()       # error notification


# ─────────────────────────────────────────────────────────────────
#  Op Codes — specific operations
# ─────────────────────────────────────────────────────────────────

class OpCode(Enum):
    """Atomic operations that can be composed in a message."""
    READ = auto()
    WRITE = auto()
    ANALYZE = auto()
    SUMMARIZE = auto()
    TRANSLATE = auto()
    TRANSFORM = auto()
    FILTER = auto()
    AGGREGATE = auto()
    COMPARE = auto()
    CLASSIFY = auto()
    GENERATE = auto()
    SEARCH = auto()
    VALIDATE = auto()
    STATUS = auto()
    SPLIT = auto()       # task decomposition
    MERGE = auto()       # result aggregation
    NOP = auto()         # no-op / padding


# ─────────────────────────────────────────────────────────────────
#  Protocol Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class ProtocolConfig:
    """
    Configuration for the protocol layer.

    Controls token budgets, separator tokens, and structural
    constraints during training and inference.
    """

    # Token budget
    max_message_tokens: int = 30
    min_message_tokens: int = 3

    # Structural tokens (from base tokenizer)
    # These are chosen to be single-token in most tokenizers
    head_token: str = "ξ"          # message header marker
    separator_token: str = "·"     # field separator
    route_token: str = "→"         # routing indicator
    end_token: str = "◊"           # end of message

    # Budget decay (for training)
    enable_budget_decay: bool = False
    decay_rate: float = 0.999       # per-episode multiplicative decay
    budget_floor: int = 5           # minimum budget after decay

    # Error injection (for robustness training)
    enable_error_injection: bool = False
    error_rate: float = 0.0         # probability of token corruption

    # Vocabulary constraints
    vocab_size: int = 0             # set from tokenizer (0 = auto)
    reserved_token_ids: list[int] = field(default_factory=list)

    def effective_budget(self, episode: int) -> int:
        """Compute the token budget for a given training episode."""
        if not self.enable_budget_decay:
            return self.max_message_tokens
        decayed = self.max_message_tokens * (self.decay_rate ** episode)
        return max(self.budget_floor, int(decayed))

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ProtocolConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─────────────────────────────────────────────────────────────────
#  Protocol Message
# ─────────────────────────────────────────────────────────────────

@dataclass
class ProtocolMessage:
    """
    A single inter-agent protocol message.

    This is the fundamental unit of Ogenti communication.
    It wraps a sequence of token IDs produced by the encoder
    and consumed by the decoder.

    Fields
    ------
    token_ids : list[int]
        The raw token IDs forming the message body.
        These come from the base model's vocabulary but carry
        protocol-specific meanings after LoRA fine-tuning.

    message_type : MessageType | None
        High-level intent (may be None during early training
        when the protocol is still forming).

    sender_id : str
        Identifier of the sending agent.

    receiver_id : str | None
        Identifier of the intended receiver (None = broadcast).

    route_chain : list[str]
        For relay messages, the ordered list of agent IDs
        the message should pass through.

    metadata : dict
        Arbitrary key-value metadata (constraints, priorities, etc.)
    """

    token_ids: list[int]
    message_type: Optional[MessageType] = None
    sender_id: str = ""
    receiver_id: Optional[str] = None
    route_chain: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    # ── Derived properties ──

    @property
    def token_count(self) -> int:
        return len(self.token_ids)

    @property
    def fingerprint(self) -> str:
        """Deterministic hash for deduplication / caching."""
        raw = json.dumps(self.token_ids, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    @property
    def is_relay(self) -> bool:
        return len(self.route_chain) > 0

    # ── Serialization ──

    def to_dict(self) -> dict:
        return {
            "token_ids": self.token_ids,
            "message_type": self.message_type.name if self.message_type else None,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "route_chain": self.route_chain,
            "metadata": self.metadata,
            "token_count": self.token_count,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProtocolMessage:
        mt = MessageType[d["message_type"]] if d.get("message_type") else None
        return cls(
            token_ids=d["token_ids"],
            message_type=mt,
            sender_id=d.get("sender_id", ""),
            receiver_id=d.get("receiver_id"),
            route_chain=d.get("route_chain", []),
            metadata=d.get("metadata", {}),
        )

    # ── Display ──

    def __repr__(self) -> str:
        mt = self.message_type.name if self.message_type else "?"
        return (
            f"ProtocolMessage("
            f"type={mt}, "
            f"tokens={self.token_count}, "
            f"from={self.sender_id!r}, "
            f"to={self.receiver_id!r}"
            f")"
        )

    def pretty(self, tokenizer=None) -> str:
        """Human-readable rendering (for debugging)."""
        if tokenizer is not None:
            decoded = tokenizer.decode(self.token_ids)
            return f"[{self.sender_id}→{self.receiver_id}] {decoded}"
        return f"[{self.sender_id}→{self.receiver_id}] ids={self.token_ids}"


# ─────────────────────────────────────────────────────────────────
#  Protocol Codec Utilities
# ─────────────────────────────────────────────────────────────────

def compute_compression_ratio(
    natural_token_count: int,
    protocol_token_count: int,
) -> float:
    """Compression ratio: how many natural tokens per protocol token."""
    if protocol_token_count == 0:
        return float("inf")
    return natural_token_count / protocol_token_count


def inject_noise(
    message: ProtocolMessage,
    error_rate: float,
    vocab_size: int,
    rng=None,
) -> ProtocolMessage:
    """
    Randomly corrupt tokens in a message for robustness training.

    Each token has `error_rate` probability of being replaced
    with a random token from the vocabulary.
    """
    import random
    rng = rng or random.Random()

    noisy_ids = []
    for tid in message.token_ids:
        if rng.random() < error_rate:
            noisy_ids.append(rng.randint(0, vocab_size - 1))
        else:
            noisy_ids.append(tid)

    return ProtocolMessage(
        token_ids=noisy_ids,
        message_type=message.message_type,
        sender_id=message.sender_id,
        receiver_id=message.receiver_id,
        route_chain=list(message.route_chain),
        metadata={**message.metadata, "_noised": True},
    )
