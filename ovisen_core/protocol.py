"""OVISEN Protocol — Embedding Message Types & Configuration

Defines the structure of compressed visual embeddings exchanged
between AI agents. Instead of sending raw images (millions of pixels),
agents send compact embedding vectors that preserve semantic content.
"""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import List, Optional
import numpy as np


class CompressionLevel(IntEnum):
    """Compression aggressiveness levels."""
    LOSSLESS = 0     # Full-dimension embedding (no compression)
    LIGHT = 1        # 2x compression, >98% fidelity
    STANDARD = 2     # 10x compression, >95% fidelity
    AGGRESSIVE = 3   # 50x compression, >90% fidelity
    EXTREME = 4      # 100x+ compression, >85% fidelity


class EmbeddingFormat(str, Enum):
    """Output embedding data formats."""
    FLOAT32 = "float32"
    FLOAT16 = "float16"
    INT8 = "int8"
    BINARY = "binary"  # 1-bit hash embedding


class MessageType(str, Enum):
    """Types of visual protocol messages."""
    EMBED = "embed"           # Image → embedding
    RECONSTRUCT = "reconstruct"  # Embedding → feature reconstruction
    COMPARE = "compare"       # Similarity between embeddings
    ROUTE = "route"           # Route to specialized vision model
    ACK = "ack"               # Acknowledgement
    ERROR = "error"           # Error in visual processing


@dataclass
class EmbeddingConfig:
    """Configuration for the visual embedding protocol."""
    # Model
    backbone: str = "clip-vit-b32"       # Vision backbone model
    lora_r: int = 16                      # LoRA rank
    lora_alpha: int = 32                  # LoRA alpha

    # Embedding dimensions
    input_dim: int = 2048                 # Original embedding dimension from backbone
    target_dim: int = 256                 # Compressed embedding dimension
    bottleneck_dim: int = 64              # Bottleneck layer for extreme compression

    # Image preprocessing
    image_size: int = 224                 # Input image resolution
    patch_size: int = 16                  # ViT patch size
    channels: int = 3                     # RGB

    # Compression
    compression_level: CompressionLevel = CompressionLevel.STANDARD
    output_format: EmbeddingFormat = EmbeddingFormat.FLOAT32

    # Training
    fidelity_weight: float = 0.4         # SSIM/LPIPS reconstruction weight
    compression_weight: float = 0.3      # Compression ratio reward weight
    usefulness_weight: float = 0.2       # Downstream task accuracy weight
    latency_weight: float = 0.1          # Inference speed weight

    @property
    def compression_ratio(self) -> float:
        """Theoretical compression ratio."""
        original_size = self.image_size * self.image_size * self.channels  # raw pixels
        compressed_size = self.target_dim * 4  # float32 bytes
        return original_size / compressed_size

    @property
    def num_patches(self) -> int:
        return (self.image_size // self.patch_size) ** 2


@dataclass
class EmbeddingMessage:
    """A visual embedding message for cross-modal AI telepathy.

    Instead of transmitting raw image data (e.g., 224×224×3 = 150,528 bytes),
    the encoder produces a compact embedding vector (e.g., 256 floats = 1,024 bytes).
    The receiving agent can directly use this embedding for downstream tasks
    without ever needing the original image.
    """
    msg_type: MessageType = MessageType.EMBED
    embedding: Optional[np.ndarray] = None       # The compressed embedding vector
    source_model: str = ""                        # Which vision model produced this
    target_dim: int = 256                         # Embedding dimensionality
    compression_ratio: float = 0.0                # Actual compression achieved
    fidelity_score: float = 0.0                   # Reconstruction quality (0–1)
    metadata: dict = field(default_factory=dict)  # Additional info (image hash, etc.)

    @property
    def byte_size(self) -> int:
        """Size of the embedding in bytes."""
        if self.embedding is not None:
            return self.embedding.nbytes
        return 0

    def to_dict(self) -> dict:
        return {
            "type": self.msg_type.value,
            "embedding": self.embedding.tolist() if self.embedding is not None else None,
            "source_model": self.source_model,
            "target_dim": self.target_dim,
            "compression_ratio": self.compression_ratio,
            "fidelity_score": self.fidelity_score,
            "byte_size": self.byte_size,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EmbeddingMessage":
        emb = np.array(data["embedding"], dtype=np.float32) if data.get("embedding") else None
        return cls(
            msg_type=MessageType(data.get("type", "embed")),
            embedding=emb,
            source_model=data.get("source_model", ""),
            target_dim=data.get("target_dim", 256),
            compression_ratio=data.get("compression_ratio", 0.0),
            fidelity_score=data.get("fidelity_score", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProtocolStats:
    """Statistics for visual protocol performance."""
    total_images_processed: int = 0
    total_bytes_saved: int = 0
    avg_compression_ratio: float = 0.0
    avg_fidelity: float = 0.0
    avg_latency_ms: float = 0.0

    @property
    def total_savings_mb(self) -> float:
        return self.total_bytes_saved / (1024 * 1024)
