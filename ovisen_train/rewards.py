"""
rewards.py — OVISEN Reward Function

4-component reward for image embedding compression:
  fidelity(0.4) + compression(0.3) + clarity(0.2) + generalization(0.1)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)


@dataclass
class RewardConfig:
    """Reward component weights."""
    fidelity_weight: float = 0.4
    compression_weight: float = 0.3
    clarity_weight: float = 0.2
    generalization_weight: float = 0.1

    # Penalties
    too_large_penalty: float = -0.5      # compressed > 50% of original
    zero_info_penalty: float = -1.0      # degenerate compression
    fidelity_floor: float = 0.5          # minimum acceptable cosine sim


class RewardFunction:
    """Compute multi-component reward for OVISEN episodes."""

    def __init__(self, config: RewardConfig | None = None):
        self.config = config or RewardConfig()

    def compute(
        self,
        original: torch.Tensor,
        compressed: torch.Tensor,
        reconstructed: torch.Tensor,
        target_ratio: float = 15.0,
    ) -> dict:
        """
        Compute reward components.

        Args:
            original: Original image embedding [B, D]
            compressed: Compressed representation [B, D']
            reconstructed: Decoded embedding [B, D]
            target_ratio: Target compression ratio

        Returns:
            dict with 'total', 'fidelity', 'compression', 'clarity', 'generalization'
        """
        # Fidelity: cosine similarity between original and reconstructed
        fidelity = F.cosine_similarity(
            original.flatten(1), reconstructed.flatten(1), dim=-1
        ).mean().item()

        # Compression: how close to target ratio
        actual_ratio = original.numel() / max(compressed.numel(), 1)
        ratio_score = 1.0 - abs(actual_ratio - target_ratio) / target_ratio
        compression = max(0.0, min(1.0, ratio_score))

        # Clarity: variance of compressed representation (avoid degenerate)
        clarity = min(1.0, compressed.var().item() * 10)

        # Generalization: placeholder — measured across categories in curriculum
        generalization = fidelity * 0.9  # proxy

        # Penalties
        penalty = 0.0
        if actual_ratio < 2.0:
            penalty += self.config.too_large_penalty
        if compressed.var().item() < 1e-6:
            penalty += self.config.zero_info_penalty
        if fidelity < self.config.fidelity_floor:
            penalty += -0.3

        total = (
            self.config.fidelity_weight * fidelity
            + self.config.compression_weight * compression
            + self.config.clarity_weight * clarity
            + self.config.generalization_weight * generalization
            + penalty
        )

        return {
            "total": total,
            "fidelity": fidelity,
            "compression": compression,
            "clarity": clarity,
            "generalization": generalization,
            "penalty": penalty,
            "actual_ratio": actual_ratio,
        }
