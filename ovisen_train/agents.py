"""
agents.py — OVISEN MAPPO Agents

Defines the ImageEncoder agent and ImageDecoder agent for MAPPO training.
Each agent wraps the underlying vision model with a value head for
PPO advantage estimation.

Follows ogenti_train.agents / phiren_train.agents pattern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, NamedTuple

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from ovisen_core.encoder import OVisenEncoder
from ovisen_core.decoder import OVisenDecoder

logger = logging.getLogger(__name__)


class ValueHead(nn.Module):
    """3-layer MLP critic for advantage estimation."""

    def __init__(self, input_size: int, hidden_size: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_size, hidden_size // 2),
            nn.GELU(),
            nn.Linear(hidden_size // 2, 1),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.net(state).squeeze(-1)


@dataclass
class AgentConfig:
    """PPO hyperparameters."""
    ppo_clip: float = 0.2
    ppo_epochs: int = 4
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    max_grad_norm: float = 1.0
    gamma: float = 0.99
    gae_lambda: float = 0.95


class RolloutEntry(NamedTuple):
    state: torch.Tensor
    action_logprob: float
    value: float
    reward: float
    done: bool


class OVisenAgents:
    """
    Manages encoder + decoder agents for OVISEN MAPPO.
    
    Encoder: Image → compressed embedding tokens
    Decoder: Compressed tokens → reconstructed embedding
    """

    def __init__(
        self,
        encoder: OVisenEncoder,
        decoder: OVisenDecoder,
        hidden_size: int = 768,
        agent_config: Optional[AgentConfig] = None,
    ):
        self.encoder = encoder
        self.decoder = decoder
        self.config = agent_config or AgentConfig()

        self.encoder_value = ValueHead(hidden_size)
        self.decoder_value = ValueHead(hidden_size)

        self.encoder_rollout: list[RolloutEntry] = []
        self.decoder_rollout: list[RolloutEntry] = []

    def clear_rollouts(self):
        self.encoder_rollout.clear()
        self.decoder_rollout.clear()

    def parameters(self):
        """Yield all trainable parameters."""
        yield from self.encoder.parameters()
        yield from self.decoder.parameters()
        yield from self.encoder_value.parameters()
        yield from self.decoder_value.parameters()

    def to(self, device: torch.device) -> "OVisenAgents":
        self.encoder.to(device)
        self.decoder.to(device)
        self.encoder_value.to(device)
        self.decoder_value.to(device)
        return self

    def compute_gae(
        self, rollout: list[RolloutEntry]
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Compute GAE advantages and returns."""
        rewards = torch.tensor([r.reward for r in rollout])
        values = torch.tensor([r.value for r in rollout])
        dones = torch.tensor([r.done for r in rollout], dtype=torch.float32)

        advantages = torch.zeros_like(rewards)
        last_adv = 0.0

        for t in reversed(range(len(rollout))):
            next_val = 0.0 if t == len(rollout) - 1 else values[t + 1]
            next_done = 1.0 if t == len(rollout) - 1 else dones[t + 1]
            delta = rewards[t] + self.config.gamma * next_val * (1 - next_done) - values[t]
            last_adv = delta + self.config.gamma * self.config.gae_lambda * (1 - next_done) * last_adv
            advantages[t] = last_adv

        returns = advantages + values
        return advantages, returns
