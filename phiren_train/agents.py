"""
agents.py — PHIREN MAPPO Agents

Defines the DetectorAgent and VerifierAgent for MAPPO training.
Each agent wraps the underlying model (PhirenDetector / PhirenCalibrator)
with a value head for PPO advantage estimation.

Follows ogenti_train.agents pattern (ValueHead + AgentPool).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, NamedTuple

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from phiren_core.detector import PhirenDetector, DetectorConfig
from phiren_core.calibrator import PhirenCalibrator, CalibratorConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Value Head (Critic)
# ─────────────────────────────────────────────────────────────────

class ValueHead(nn.Module):
    """
    3-layer MLP critic for advantage estimation.
    Takes a state representation and outputs V(s).
    """

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
        """Returns V(s) — scalar value estimate."""
        return self.net(state).squeeze(-1)


# ─────────────────────────────────────────────────────────────────
#  Agent Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    """PPO hyperparameters for agents."""
    ppo_clip: float = 0.2
    ppo_epochs: int = 4
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    max_grad_norm: float = 1.0
    gamma: float = 0.99
    gae_lambda: float = 0.95


# ─────────────────────────────────────────────────────────────────
#  Rollout Buffer
# ─────────────────────────────────────────────────────────────────

class RolloutEntry(NamedTuple):
    """Single step in a rollout."""
    state: torch.Tensor        # state representation
    action_logprob: float      # log probability of the taken action
    value: float               # V(s) estimate
    reward: float              # received reward
    done: bool                 # episode terminated


class RolloutBuffer:
    """
    Buffer for collecting rollout data and computing GAE advantages.
    """

    def __init__(self):
        self.entries: list[RolloutEntry] = []

    def add(self, entry: RolloutEntry) -> None:
        self.entries.append(entry)

    def clear(self) -> None:
        self.entries.clear()

    def __len__(self) -> int:
        return len(self.entries)

    def compute_gae(
        self,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        last_value: float = 0.0,
    ) -> tuple[list[float], list[float]]:
        """
        Compute Generalized Advantage Estimation.

        Returns: (advantages, returns)
        """
        advantages = []
        returns = []
        gae = 0.0

        values = [e.value for e in self.entries] + [last_value]
        rewards = [e.reward for e in self.entries]
        dones = [e.done for e in self.entries]

        for t in reversed(range(len(self.entries))):
            if dones[t]:
                next_value = 0.0
                gae = 0.0
            else:
                next_value = values[t + 1]

            delta = rewards[t] + gamma * next_value - values[t]
            gae = delta + gamma * gae_lambda * (1.0 - float(dones[t])) * gae
            advantages.insert(0, gae)
            returns.insert(0, gae + values[t])

        return advantages, returns

    def get_batches(
        self,
        batch_size: int,
        advantages: list[float],
        returns: list[float],
    ):
        """Yield mini-batches for PPO update."""
        n = len(self.entries)
        indices = np.random.permutation(n)

        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            batch_idx = indices[start:end]

            states = torch.stack([self.entries[i].state for i in batch_idx])
            old_logprobs = torch.tensor(
                [self.entries[i].action_logprob for i in batch_idx],
                dtype=torch.float32,
            )
            batch_advantages = torch.tensor(
                [advantages[i] for i in batch_idx],
                dtype=torch.float32,
            )
            batch_returns = torch.tensor(
                [returns[i] for i in batch_idx],
                dtype=torch.float32,
            )

            yield states, old_logprobs, batch_advantages, batch_returns


# ─────────────────────────────────────────────────────────────────
#  Detector Agent
# ─────────────────────────────────────────────────────────────────

class DetectorAgent(nn.Module):
    """
    Wraps PhirenDetector with a ValueHead for PPO training.

    The detector agent:
      - Extracts claims from text (policy action)
      - Runs NLI verification (policy action)
      - Gets reward from factuality + helpfulness
    """

    def __init__(
        self,
        detector: PhirenDetector,
        value_hidden_size: int = 256,
    ):
        super().__init__()
        self.detector = detector
        self.value_head = ValueHead(
            detector.config.hidden_size,
            value_hidden_size,
        )
        self.buffer = RolloutBuffer()

    def get_state(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """
        Extract state representation for the value function.
        Uses mean pooling over the last hidden states.
        """
        return hidden_states.mean(dim=1)  # [B, H]

    def estimate_value(self, state: torch.Tensor) -> torch.Tensor:
        """V(s) estimate."""
        return self.value_head(state)

    def trainable_parameters(self) -> list[nn.Parameter]:
        """All trainable params (detector LoRA + heads + value head)."""
        params = list(self.detector.trainable_parameters())
        params.extend(self.value_head.parameters())
        return params


# ─────────────────────────────────────────────────────────────────
#  Verifier Agent
# ─────────────────────────────────────────────────────────────────

class VerifierAgent(nn.Module):
    """
    Wraps PhirenCalibrator with a ValueHead for PPO training.

    The verifier agent:
      - Calibrates confidence scores (policy action)
      - Produces final verdicts considering calibrated scores
      - Gets reward from calibration + robustness
    """

    def __init__(
        self,
        calibrator: PhirenCalibrator,
        state_size: int = 64,
        value_hidden_size: int = 128,
    ):
        super().__init__()
        self.calibrator = calibrator
        self.state_size = state_size

        # State encoder: takes verification features → state
        # Features: [num_claims, avg_confidence, max_confidence,
        #            supported_ratio, contradicted_ratio, ece, ...]
        self.state_encoder = nn.Sequential(
            nn.Linear(8, state_size),
            nn.GELU(),
            nn.Linear(state_size, state_size),
        )

        self.value_head = ValueHead(state_size, value_hidden_size)
        self.buffer = RolloutBuffer()

    def encode_state(
        self,
        num_claims: int,
        avg_confidence: float,
        max_confidence: float,
        supported_ratio: float,
        contradicted_ratio: float,
        unverifiable_ratio: float,
        ece: float,
        factuality: float,
    ) -> torch.Tensor:
        """Encode verification features into a state vector."""
        features = torch.tensor([
            num_claims / 20.0,  # normalized
            avg_confidence,
            max_confidence,
            supported_ratio,
            contradicted_ratio,
            unverifiable_ratio,
            ece,
            factuality,
        ], dtype=torch.float32).unsqueeze(0)  # [1, 8]

        return self.state_encoder(features).squeeze(0)  # [state_size]

    def estimate_value(self, state: torch.Tensor) -> torch.Tensor:
        """V(s) estimate."""
        return self.value_head(state)

    def trainable_parameters(self) -> list[nn.Parameter]:
        """All trainable params."""
        params = list(self.state_encoder.parameters())
        params.extend(self.value_head.parameters())
        if self.calibrator.scaler is not None:
            params.extend(self.calibrator.scaler.parameters())
        return params


# ─────────────────────────────────────────────────────────────────
#  Agent Pool
# ─────────────────────────────────────────────────────────────────

class AgentPool:
    """
    Manages pairs of (DetectorAgent, VerifierAgent).

    Supports shared-model mode where detector and verifier
    share a backbone with separate LoRA adapters.
    """

    def __init__(self, agent_config: Optional[AgentConfig] = None):
        self.config = agent_config or AgentConfig()
        self.detector_agent: Optional[DetectorAgent] = None
        self.verifier_agent: Optional[VerifierAgent] = None
        self._shared_model = False

    def build_pair(
        self,
        detector_config: Optional[DetectorConfig] = None,
        calibrator_config: Optional[CalibratorConfig] = None,
        shared_model: bool = True,
        device: str = "auto",
    ) -> tuple[DetectorAgent, VerifierAgent]:
        """
        Build a (DetectorAgent, VerifierAgent) pair.

        If shared_model=True, detector and verifier share the same
        backbone LLM (loaded once) with separate LoRA adapters.
        """
        detector_config = detector_config or DetectorConfig()
        calibrator_config = calibrator_config or CalibratorConfig()

        logger.info(f"Building agent pair (shared_model={shared_model})")

        # Build detector
        detector = PhirenDetector.build(detector_config, device=device)
        self.detector_agent = DetectorAgent(detector)

        # Build calibrator
        calibrator = PhirenCalibrator(calibrator_config)
        self.verifier_agent = VerifierAgent(
            calibrator,
            state_size=64,
            value_hidden_size=128,
        )

        self._shared_model = shared_model

        total_params = sum(
            p.numel() for p in self.detector_agent.trainable_parameters()
        ) + sum(
            p.numel() for p in self.verifier_agent.trainable_parameters()
        )
        logger.info(f"Agent pair built | total trainable: {total_params:,}")

        return self.detector_agent, self.verifier_agent

    def clear_buffers(self) -> None:
        """Clear rollout buffers for both agents."""
        if self.detector_agent:
            self.detector_agent.buffer.clear()
        if self.verifier_agent:
            self.verifier_agent.buffer.clear()

    def parameter_summary(self) -> dict:
        """Get parameter count summary."""
        summary = {}
        if self.detector_agent:
            det_params = self.detector_agent.detector.parameter_count()
            det_value = sum(p.numel() for p in self.detector_agent.value_head.parameters())
            summary["detector"] = {
                "model_trainable": det_params["trainable"],
                "model_total": det_params["total"],
                "value_head": det_value,
            }
        if self.verifier_agent:
            ver_params = sum(p.numel() for p in self.verifier_agent.trainable_parameters())
            summary["verifier"] = {
                "trainable": ver_params,
            }
        return summary
