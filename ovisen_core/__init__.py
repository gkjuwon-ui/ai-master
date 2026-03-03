"""OVISEN Core — Image Embedding Compression Protocol Engine

AI-to-AI visual communication doesn't need raw images.
OVISEN trains vision models to convert images into compressed
high-dimensional embeddings that downstream AI agents can directly consume.

Architecture:
  Image → VisionEncoder (ViT + LoRA) → Compressed Embedding
  Compressed Embedding → EmbeddingDecoder → Reconstructed Features
  MARL: Encoder + Decoder compete to minimize embedding dimensions
         while maximizing reconstruction fidelity (SSIM/LPIPS).
"""

from .protocol import (
    EmbeddingConfig,
    EmbeddingMessage,
    CompressionLevel,
)
from .encoder import VisionEncoder
from .decoder import EmbeddingDecoder
from .channel import EmbeddingChannel

__all__ = [
    "EmbeddingConfig",
    "EmbeddingMessage",
    "CompressionLevel",
    "VisionEncoder",
    "EmbeddingDecoder",
    "EmbeddingChannel",
]

__version__ = "0.1.0"
