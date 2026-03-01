"""
agents.py — MARL Agent Wrappers

Wraps OgentiEncoder and OgentiDecoder into MARL agent abstractions
compatible with the MAPPO training loop.

Architecture
------------
  ┌─────────────────────┐
  │    MARLAgent         │
  │  ┌───────────────┐  │
  │  │ Encoder/Decoder│  │  ← LoRA-adapted LLM
  │  └───────────────┘  │
  │  ┌───────────────┐  │
  │  │  Value Head    │  │  ← Centralized critic (shared)
  │  └───────────────┘  │
  │  ┌───────────────┐  │
  │  │  Policy Head   │  │  ← Per-agent (decentralized)
  │  └───────────────┘  │
  └─────────────────────┘

The MAPPO algorithm uses:
  - Decentralized actors (each agent has its own policy head)
  - Centralized critic (shared value function that sees global state)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import torch
import torch.nn as nn

from ogenti_core.encoder import OgentiEncoder, EncoderConfig
from ogenti_core.decoder import OgentiDecoder, DecoderConfig
from ogenti_core.protocol import ProtocolConfig, ProtocolMessage

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Value Head (Centralized Critic)
# ─────────────────────────────────────────────────────────────────

class ValueHead(nn.Module):
    """
    Centralized value function for MAPPO.

    Takes a state representation (e.g. concatenation of observations
    from all agents) and outputs a scalar value estimate.
    """

    def __init__(self, input_dim: int = 3072, hidden_dim: int = 512):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        state : (batch, input_dim)

        Returns
        -------
        value : (batch, 1)
        """
        return self.net(state)


# ─────────────────────────────────────────────────────────────────
#  MARL Agent Config
# ─────────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    """Configuration for a MARL agent."""

    agent_id: str = "agent_0"
    role: str = "encoder"   # "encoder" | "decoder" | "both"
    model_name: str = "Qwen/Qwen2.5-3B-Instruct"

    # PPO hyperparams (per-agent)
    clip_eps: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    max_grad_norm: float = 1.0

    # GAE
    gamma: float = 0.99
    gae_lambda: float = 0.95


# ─────────────────────────────────────────────────────────────────
#  Rollout Buffer
# ─────────────────────────────────────────────────────────────────

@dataclass
class RolloutEntry:
    """A single step in the rollout buffer."""

    observation: str                   # NL instruction or protocol tokens
    action_token_ids: list[int]        # Generated token IDs
    log_probs: list[float]             # Log probability for each token
    value: float = 0.0                 # V(s) from critic
    reward: float = 0.0                # R from reward function
    advantage: float = 0.0            # GAE advantage
    returns: float = 0.0              # Discounted return


class RolloutBuffer:
    """
    Collects rollout data across episodes for PPO updates.
    """

    def __init__(self, max_size: int = 2048):
        self.max_size = max_size
        self.entries: list[RolloutEntry] = []

    def add(self, entry: RolloutEntry) -> None:
        self.entries.append(entry)
        if len(self.entries) > self.max_size:
            self.entries.pop(0)

    def compute_gae(self, gamma: float = 0.99, lam: float = 0.95) -> None:
        """Compute Generalized Advantage Estimation."""
        n = len(self.entries)
        if n == 0:
            return

        # In our setting each episode is a single step
        # (encode → decode → reward), so GAE simplifies to:
        # A = R - V(s)
        for entry in self.entries:
            entry.advantage = entry.reward - entry.value
            entry.returns = entry.reward

    def get_batches(self, batch_size: int = 64):
        """Yield minibatches for PPO update."""
        indices = list(range(len(self.entries)))
        import random
        random.shuffle(indices)

        for start in range(0, len(indices), batch_size):
            batch_idx = indices[start:start + batch_size]
            yield [self.entries[i] for i in batch_idx]

    def clear(self) -> None:
        self.entries.clear()

    def __len__(self) -> int:
        return len(self.entries)


# ─────────────────────────────────────────────────────────────────
#  Encoder Agent
# ─────────────────────────────────────────────────────────────────

class EncoderAgent(nn.Module):
    """
    MARL agent that encodes NL → protocol.

    Wraps OgentiEncoder + policy head (the LoRA layers themselves
    act as the policy) + shared value head reference.
    """

    def __init__(
        self,
        encoder: OgentiEncoder,
        value_head: ValueHead,
        config: AgentConfig,
    ):
        super().__init__()
        self.encoder = encoder
        self.value_head = value_head
        self.config = config
        self.rollout = RolloutBuffer()

    @classmethod
    def build(
        cls,
        agent_config: Optional[AgentConfig] = None,
        encoder_config: Optional[EncoderConfig] = None,
        protocol_config: Optional[ProtocolConfig] = None,
        value_head: Optional[ValueHead] = None,
    ) -> EncoderAgent:
        """Build an encoder agent from scratch."""
        cfg = agent_config or AgentConfig(role="encoder")
        enc = OgentiEncoder.build(encoder_config, protocol_config)
        vh = value_head or ValueHead()
        return cls(enc, vh, cfg)

    def act(
        self,
        instruction: str,
        max_tokens: Optional[int] = None,
    ) -> tuple[ProtocolMessage, list[float]]:
        """
        Generate a protocol message with log-probabilities.

        Returns (message, log_probs) for PPO.
        """
        sequences, scores = self.encoder.encode_for_training(
            instruction, max_tokens=max_tokens
        )

        # Extract protocol tokens (strip prompt)
        prompt_text = (
            f"{self.encoder.config.encode_prefix}"
            f"{instruction}"
            f"{self.encoder.config.encode_suffix}"
        )
        prompt_ids = self.encoder.tokenizer(prompt_text, return_tensors="pt")["input_ids"]
        prompt_len = prompt_ids.shape[1]

        token_ids = sequences[0, prompt_len:].tolist()
        token_ids = self.encoder._strip_special(token_ids)

        # Compute log probs from scores
        log_probs = []
        for i, score in enumerate(scores):
            if i >= len(token_ids):
                break
            probs = torch.softmax(score[0], dim=-1)
            token_id = token_ids[i] if i < len(token_ids) else 0
            lp = torch.log(probs[token_id] + 1e-8).item()
            log_probs.append(lp)

        message = ProtocolMessage(
            token_ids=token_ids,
            sender_id=self.config.agent_id,
        )

        return message, log_probs

    def get_value(self, state_embedding: torch.Tensor) -> float:
        """Get value estimate from centralized critic."""
        with torch.no_grad():
            return self.value_head(state_embedding).item()


# ─────────────────────────────────────────────────────────────────
#  Decoder Agent
# ─────────────────────────────────────────────────────────────────

class DecoderAgent(nn.Module):
    """
    MARL agent that decodes protocol → NL/action.
    """

    def __init__(
        self,
        decoder: OgentiDecoder,
        value_head: ValueHead,
        config: AgentConfig,
    ):
        super().__init__()
        self.decoder = decoder
        self.value_head = value_head
        self.config = config
        self.rollout = RolloutBuffer()

    @classmethod
    def build(
        cls,
        agent_config: Optional[AgentConfig] = None,
        decoder_config: Optional[DecoderConfig] = None,
        protocol_config: Optional[ProtocolConfig] = None,
        value_head: Optional[ValueHead] = None,
    ) -> DecoderAgent:
        """Build a decoder agent from scratch."""
        cfg = agent_config or AgentConfig(agent_id="agent_1", role="decoder")
        dec = OgentiDecoder.build(decoder_config, protocol_config)
        vh = value_head or ValueHead()
        return cls(dec, vh, cfg)

    def act(
        self,
        message: ProtocolMessage,
    ) -> tuple[str, list[float]]:
        """
        Decode a protocol message with log-probabilities.

        Returns (decoded_text, log_probs) for PPO.
        """
        sequences, scores = self.decoder.decode_for_training(message)

        # Extract decoded tokens (strip prompt)
        proto_text = self.decoder.tokenizer.decode(
            message.token_ids, skip_special_tokens=False
        )
        prompt = f"{self.decoder.config.decode_prefix}{proto_text}{self.decoder.config.decode_suffix}"
        prompt_ids = self.decoder.tokenizer(prompt, return_tensors="pt")["input_ids"]
        prompt_len = prompt_ids.shape[1]

        decoded_ids = sequences[0, prompt_len:].tolist()
        decoded_text = self.decoder.tokenizer.decode(
            decoded_ids, skip_special_tokens=True
        ).strip()

        # Compute log probs
        log_probs = []
        for i, score in enumerate(scores):
            if i >= len(decoded_ids):
                break
            probs = torch.softmax(score[0], dim=-1)
            token_id = decoded_ids[i] if i < len(decoded_ids) else 0
            lp = torch.log(probs[token_id] + 1e-8).item()
            log_probs.append(lp)

        return decoded_text, log_probs

    def get_value(self, state_embedding: torch.Tensor) -> float:
        """Get value estimate from centralized critic."""
        with torch.no_grad():
            return self.value_head(state_embedding).item()


# ─────────────────────────────────────────────────────────────────
#  Agent Pool
# ─────────────────────────────────────────────────────────────────

class AgentPool:
    """
    Manages a pool of encoder/decoder agents for MARL.

    In the simplest case (Phase 0-1): 1 encoder + 1 decoder.
    In Phase 2+: multiple agents for multi-hop relay chains.
    """

    def __init__(self):
        self.encoders: dict[str, EncoderAgent] = {}
        self.decoders: dict[str, DecoderAgent] = {}
        self.shared_value_head: Optional[ValueHead] = None

    def add_encoder(self, agent: EncoderAgent) -> None:
        self.encoders[agent.config.agent_id] = agent

    def add_decoder(self, agent: DecoderAgent) -> None:
        self.decoders[agent.config.agent_id] = agent

    @classmethod
    def build_pair(
        cls,
        protocol_config: Optional[ProtocolConfig] = None,
    ) -> AgentPool:
        """Build the default encoder-decoder pair."""
        pool = cls()
        proto_cfg = protocol_config or ProtocolConfig()

        # Shared value head (centralized critic)
        value_head = ValueHead()
        pool.shared_value_head = value_head

        encoder_agent = EncoderAgent.build(
            agent_config=AgentConfig(agent_id="encoder_0", role="encoder"),
            protocol_config=proto_cfg,
            value_head=value_head,
        )
        decoder_agent = DecoderAgent.build(
            agent_config=AgentConfig(agent_id="decoder_0", role="decoder"),
            protocol_config=proto_cfg,
            value_head=value_head,
        )

        pool.add_encoder(encoder_agent)
        pool.add_decoder(decoder_agent)

        return pool

    def get_encoder(self, agent_id: str = "encoder_0") -> EncoderAgent:
        return self.encoders[agent_id]

    def get_decoder(self, agent_id: str = "decoder_0") -> DecoderAgent:
        return self.decoders[agent_id]

    def all_parameters(self):
        """Yield all trainable parameters across all agents + value head."""
        for enc in self.encoders.values():
            yield from enc.encoder.parameters()
        for dec in self.decoders.values():
            yield from dec.decoder.parameters()
        if self.shared_value_head is not None:
            yield from self.shared_value_head.parameters()

    def trainable_parameter_count(self) -> int:
        return sum(
            p.numel() for p in self.all_parameters() if p.requires_grad
        )

    def __repr__(self) -> str:
        return (
            f"AgentPool(encoders={list(self.encoders.keys())}, "
            f"decoders={list(self.decoders.keys())})"
        )
