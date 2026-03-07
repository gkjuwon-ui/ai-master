"""OVISEN Vision Encoder — Image → Compressed Embedding

Takes raw images and produces compressed embedding vectors using a
vision backbone (CLIP, DINOv2, SigLIP, EVA-02) with LoRA adaptation.

The encoder learns to compress visual information into the minimal
number of dimensions while preserving semantic content that downstream
AI agents need.

Architecture:
  Image → ViT Backbone → [CLS] token → LoRA Projection Head → Compressed Embedding
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import torch
import torch.nn as nn
import numpy as np

from .protocol import EmbeddingConfig, EmbeddingMessage, MessageType

logger = logging.getLogger("ovisen.encoder")


class CompressionHead(nn.Module):
    """Learnable compression head: maps backbone embeddings → compact vectors.

    Uses a bottleneck architecture trained via MARL to discover the optimal
    embedding structure for visual telepathy.
    """

    def __init__(self, input_dim: int, target_dim: int, bottleneck_dim: int = 64):
        super().__init__()
        self.compress = nn.Sequential(
            nn.Linear(input_dim, input_dim // 2),
            nn.GELU(),
            nn.LayerNorm(input_dim // 2),
            nn.Dropout(0.1),
            nn.Linear(input_dim // 2, bottleneck_dim),
            nn.GELU(),
            nn.LayerNorm(bottleneck_dim),
            nn.Linear(bottleneck_dim, target_dim),
        )
        self.norm = nn.LayerNorm(target_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.norm(self.compress(x))


class VisionEncoder(nn.Module):
    """OVISEN Vision Encoder: Image → Compressed Semantic Embedding.

    The encoder wraps a pretrained vision backbone (frozen) and adds
    a trainable LoRA-adapted compression head that learns to produce
    minimal-dimension embeddings preserving semantic content.

    During MARL training:
    - The encoder agent tries to compress as much as possible
    - The decoder agent tries to reconstruct/use the embedding
    - They converge on an emergent visual protocol
    """

    def __init__(self, config: EmbeddingConfig):
        super().__init__()
        self.config = config

        # Compression head (this is what gets trained via MARL)
        self.compression_head = CompressionHead(
            input_dim=config.input_dim,
            target_dim=config.target_dim,
            bottleneck_dim=config.bottleneck_dim,
        )

        # Value head for PPO (estimates expected compression quality)
        self.value_head = nn.Sequential(
            nn.Linear(config.target_dim, 128),
            nn.GELU(),
            nn.Linear(128, 1),
        )

        self._backbone = None  # Lazy-loaded vision backbone

    def _load_backbone(self):
        """Lazy-load the vision backbone on first use."""
        if self._backbone is not None:
            return

        try:
            from transformers import AutoModel, AutoProcessor
            model_id = {
                "clip-vit-b32": "openai/clip-vit-base-patch32",
                "clip-vit-l14": "openai/clip-vit-large-patch14",
                "siglip-so400m": "google/siglip-so400m-patch14-384",
                "dinov2-vit-b14": "facebook/dinov2-base",
                "dinov2-vit-l14": "facebook/dinov2-large",
                "eva02-vit-l": "Yuxin-CV/EVA-02/eva02_L_pt_m38m_p14to16",
            }.get(self.config.backbone, self.config.backbone)

            self._backbone = AutoModel.from_pretrained(model_id, trust_remote_code=True)
            self._processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

            # Freeze backbone
            for param in self._backbone.parameters():
                param.requires_grad = False

            logger.info(f"Loaded vision backbone: {model_id}")
        except Exception as e:
            logger.warning(f"Could not load backbone {self.config.backbone}: {e}. Using random projection.")
            self._backbone = nn.Linear(self.config.input_dim, self.config.input_dim)

    def encode_image(self, image: torch.Tensor) -> EmbeddingMessage:
        """Encode a preprocessed image tensor → compressed embedding message.

        Args:
            image: Preprocessed image tensor [B, C, H, W]

        Returns:
            EmbeddingMessage with compressed embedding
        """
        with torch.no_grad():
            # Get backbone features
            if hasattr(self._backbone, 'get_image_features'):
                features = self._backbone.get_image_features(image)
            elif hasattr(self._backbone, 'forward'):
                out = self._backbone(image)
                features = out.last_hidden_state[:, 0]  # CLS token
            else:
                features = self._backbone(image)

        # Compress through learned head
        compressed = self.compression_head(features)

        # Calculate compression ratio
        original_size = image.numel() * 4  # float32
        compressed_size = compressed.numel() * 4
        ratio = original_size / compressed_size

        embedding_np = compressed.detach().cpu().numpy().flatten()

        return EmbeddingMessage(
            msg_type=MessageType.EMBED,
            embedding=embedding_np,
            source_model=self.config.backbone,
            target_dim=self.config.target_dim,
            compression_ratio=ratio,
        )

    def forward(self, backbone_features: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass for MARL training.

        Args:
            backbone_features: Pre-extracted backbone features [B, input_dim]

        Returns:
            (compressed_embedding, value_estimate)
        """
        compressed = self.compression_head(backbone_features)
        value = self.value_head(compressed)
        return compressed, value

    def get_embedding_dim(self) -> int:
        return self.config.target_dim
