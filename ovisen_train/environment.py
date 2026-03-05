"""
environment.py — OVISEN Training Environment

Image dataset loading and MARL episode management.
Generates episodes: load image → encode → add noise → decode → score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import torch
import numpy as np

logger = logging.getLogger(__name__)


class ImageCategory(Enum):
    NATURAL = "natural"
    SYNTHETIC = "synthetic"
    MEDICAL = "medical"
    SATELLITE = "satellite"
    DOCUMENT = "document"
    ART = "art"


@dataclass
class ImageTask:
    """A single image compression task."""
    image_id: str
    category: ImageCategory
    original_embedding: Optional[torch.Tensor] = None
    target_dim: int = 64
    difficulty: float = 0.5  # 0.0=easy, 1.0=hard


@dataclass
class EpisodeResult:
    """Result from one encoding-decoding episode."""
    fidelity: float        # cosine sim between original and reconstructed
    compression_ratio: float  # original_dim / compressed_dim
    latency_ms: float      # encoding + decoding time
    category: ImageCategory
    task: ImageTask


class OVisenEnvironment:
    """
    MAPPO environment for OVISEN training.

    Each episode:
    1. Sample image batch from dataset
    2. Encoder compresses to protocol tokens
    3. Channel adds noise (robustness training)
    4. Decoder reconstructs embedding
    5. Compute reward (fidelity + compression + clarity + generalization)
    """

    def __init__(
        self,
        dataset_path: str = "",
        batch_size: int = 8,
        noise_std: float = 0.01,
        target_compression: float = 15.0,
    ):
        self.dataset_path = dataset_path
        self.batch_size = batch_size
        self.noise_std = noise_std
        self.target_compression = target_compression
        self._tasks: list[ImageTask] = []
        self._episode = 0

    def load_dataset(self, path: str) -> int:
        """Load image dataset. Returns number of images loaded."""
        self.dataset_path = path
        logger.info(f"Loading image dataset from {path}")
        # Actual loading deferred to RunPod worker
        return 0

    def sample_batch(self) -> list[ImageTask]:
        """Sample a batch of image tasks."""
        if not self._tasks:
            return [
                ImageTask(
                    image_id=f"img_{i}",
                    category=ImageCategory.NATURAL,
                    difficulty=min(1.0, self._episode / 500),
                )
                for i in range(self.batch_size)
            ]
        indices = np.random.choice(len(self._tasks), self.batch_size, replace=True)
        return [self._tasks[int(i)] for i in indices]

    def step(self) -> int:
        """Advance episode counter."""
        self._episode += 1
        return self._episode

    def add_channel_noise(self, embedding: torch.Tensor) -> torch.Tensor:
        """Add Gaussian noise to simulate channel imperfections."""
        noise = torch.randn_like(embedding) * self.noise_std
        return embedding + noise
