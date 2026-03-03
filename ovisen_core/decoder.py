"""OVISEN Embedding Decoder — Compressed Embedding → Feature Reconstruction

The decoder agent receives compressed embeddings from the encoder and
attempts to reconstruct the original feature representation. During MARL
training, the decoder provides the fidelity signal — if it can reconstruct
well, the compression is working.

In production, downstream AI agents use the decoder to:
1. Verify embedding integrity
2. Extract task-specific features from the compressed representation
3. Perform similarity matching against embedding databases
"""

import logging
from typing import Tuple

import torch
import torch.nn as nn

from .protocol import EmbeddingConfig

logger = logging.getLogger("ovisen.decoder")


class ReconstructionHead(nn.Module):
    """Decoder head: maps compressed embeddings → reconstructed features."""

    def __init__(self, target_dim: int, output_dim: int, bottleneck_dim: int = 64):
        super().__init__()
        self.reconstruct = nn.Sequential(
            nn.Linear(target_dim, bottleneck_dim),
            nn.GELU(),
            nn.LayerNorm(bottleneck_dim),
            nn.Linear(bottleneck_dim, output_dim // 2),
            nn.GELU(),
            nn.LayerNorm(output_dim // 2),
            nn.Dropout(0.1),
            nn.Linear(output_dim // 2, output_dim),
        )
        self.norm = nn.LayerNorm(output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.norm(self.reconstruct(x))


class EmbeddingDecoder(nn.Module):
    """OVISEN Embedding Decoder: Compressed Embedding → Original Feature Space.

    During MARL training, the decoder acts as the second agent:
    - It receives the compressed embedding from the encoder
    - It tries to reconstruct the original backbone features
    - The reconstruction quality (SSIM/cosine similarity) feeds into the reward

    This creates a cooperative pressure: the encoder must preserve enough
    information for the decoder to succeed, while minimizing dimensions.
    """

    def __init__(self, config: EmbeddingConfig):
        super().__init__()
        self.config = config

        self.reconstruction_head = ReconstructionHead(
            target_dim=config.target_dim,
            output_dim=config.input_dim,
            bottleneck_dim=config.bottleneck_dim,
        )

        # Value head for PPO
        self.value_head = nn.Sequential(
            nn.Linear(config.input_dim, 256),
            nn.GELU(),
            nn.Linear(256, 1),
        )

        # Task head: downstream classification probe
        self.task_head = nn.Sequential(
            nn.Linear(config.input_dim, 512),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(512, 1000),  # ImageNet-1K classes as proxy task
        )

    def reconstruct(self, compressed: torch.Tensor) -> torch.Tensor:
        """Reconstruct original feature space from compressed embedding.

        Args:
            compressed: Compressed embedding [B, target_dim]

        Returns:
            Reconstructed features [B, input_dim]
        """
        return self.reconstruction_head(compressed)

    def forward(self, compressed: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass for MARL training.

        Args:
            compressed: Compressed embedding from encoder [B, target_dim]

        Returns:
            (reconstructed_features, task_logits, value_estimate)
        """
        reconstructed = self.reconstruction_head(compressed)
        task_logits = self.task_head(reconstructed)
        value = self.value_head(reconstructed)
        return reconstructed, task_logits, value

    def compute_fidelity(
        self,
        compressed: torch.Tensor,
        original_features: torch.Tensor,
    ) -> dict:
        """Compute reconstruction fidelity metrics.

        Returns dict with:
          - cosine_sim: Cosine similarity between original and reconstructed
          - mse: Mean squared error
          - fidelity: Combined fidelity score (0–1)
        """
        reconstructed = self.reconstruction_head(compressed)

        # Cosine similarity
        cos_sim = nn.functional.cosine_similarity(
            reconstructed, original_features, dim=-1
        ).mean().item()

        # MSE
        mse = nn.functional.mse_loss(reconstructed, original_features).item()

        # Combined fidelity (weighted)
        fidelity = max(0.0, cos_sim) * 0.7 + max(0.0, 1.0 - mse) * 0.3

        return {
            "cosine_similarity": round(cos_sim, 4),
            "mse": round(mse, 6),
            "fidelity": round(fidelity, 4),
        }
