"""OVISEN Embedding Channel — End-to-End Pipeline & Token Budget Routing

The EmbeddingChannel wraps the full encoder→decoder pipeline and enforces
token budget constraints. In production, the channel:

1. Receives raw images
2. Encodes → compressed embeddings via VisionEncoder
3. Optionally reconstructs → via EmbeddingDecoder (for fidelity checks)
4. Routes embeddings to downstream agents respecting byte budgets

During MARL training, the channel manages the reward calculation by
combining signals from fidelity, compression ratio, and task performance.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import torch
import torch.nn as nn

from .protocol import (
    CompressionLevel,
    EmbeddingConfig,
    EmbeddingFormat,
    EmbeddingMessage,
    MessageType,
    ProtocolStats,
)
from .encoder import VisionEncoder
from .decoder import EmbeddingDecoder

logger = logging.getLogger("ovisen.channel")


# Compression-level → target_dim multiplier
_COMPRESSION_DIM_SCALE = {
    CompressionLevel.LOSSLESS: 1.0,
    CompressionLevel.LIGHT: 0.75,
    CompressionLevel.STANDARD: 0.5,
    CompressionLevel.AGGRESSIVE: 0.25,
    CompressionLevel.EXTREME: 0.125,
}


@dataclass
class ChannelReward:
    """Decomposed reward signal for MARL training."""
    fidelity: float          # How well decoder reconstructs
    compression: float       # How much we compressed
    task_performance: float  # Downstream task accuracy
    latency: float           # Speed bonus
    total: float             # Weighted combination


class EmbeddingChannel(nn.Module):
    """End-to-end OVISEN channel: Image → Compressed Embedding → Routing.

    Manages the cooperative encoder–decoder pair and enforces token budgets.
    """

    def __init__(self, config: EmbeddingConfig, device: str = "cpu"):
        super().__init__()
        self.config = config
        self.device = device

        self.encoder = VisionEncoder(config).to(device)
        self.decoder = EmbeddingDecoder(config).to(device)

        # Running statistics
        self.stats = ProtocolStats()

    # ---------- inference ----------

    @torch.no_grad()
    def embed(
        self,
        pixel_values: torch.Tensor,
        compression: CompressionLevel = CompressionLevel.STANDARD,
        fmt: EmbeddingFormat = EmbeddingFormat.FLOAT16,
    ) -> EmbeddingMessage:
        """Encode an image to a compressed embedding message.

        Args:
            pixel_values: Preprocessed image tensor [B, 3, H, W]
            compression: Target compression level
            fmt: Wire format for the embedding

        Returns:
            EmbeddingMessage ready for transmission
        """
        self.encoder.eval()
        t0 = time.perf_counter()

        pixel_values = pixel_values.to(self.device)
        msg = self.encoder.encode_image(pixel_values, fmt)

        elapsed = time.perf_counter() - t0
        self.stats.messages_sent += 1
        self.stats.total_compressed_bytes += msg.embedding.nbytes
        self.stats.total_latency_ms += elapsed * 1000

        return msg

    @torch.no_grad()
    def reconstruct(self, msg: EmbeddingMessage) -> torch.Tensor:
        """Reconstruct original features from an embedding message.

        Args:
            msg: An EmbeddingMessage (from embed() or received over wire)

        Returns:
            Reconstructed feature tensor [B, input_dim]
        """
        self.decoder.eval()
        compressed = torch.tensor(
            msg.embedding, dtype=torch.float32
        ).unsqueeze(0).to(self.device)
        return self.decoder.reconstruct(compressed)

    @torch.no_grad()
    def verify(self, msg: EmbeddingMessage, pixel_values: torch.Tensor) -> dict:
        """Verify fidelity of a compressed embedding against the source image.

        Returns fidelity metrics dict.
        """
        self.encoder.eval()
        self.decoder.eval()

        pixel_values = pixel_values.to(self.device)

        # Get original features
        original_features = self.encoder.extract_features(pixel_values)

        # Get compressed tensor
        compressed = torch.tensor(
            msg.embedding, dtype=torch.float32
        ).unsqueeze(0).to(self.device)

        return self.decoder.compute_fidelity(compressed, original_features)

    # ---------- MARL training ----------

    def forward(
        self,
        pixel_values: torch.Tensor,
        labels: Optional[torch.Tensor] = None,
    ) -> Tuple[ChannelReward, dict]:
        """Full forward pass for MARL training.

        Encoder compresses, decoder reconstructs. Combined reward is returned.

        Args:
            pixel_values: [B, 3, H, W]
            labels: Optional classification labels [B] for task reward

        Returns:
            (ChannelReward, info_dict)
        """
        pixel_values = pixel_values.to(self.device)

        # ---------- encoder ----------
        original_features = self.encoder.extract_features(pixel_values)
        compressed, enc_value = self.encoder(pixel_values)

        # ---------- decoder ----------
        reconstructed, task_logits, dec_value = self.decoder(compressed)

        # ---------- fidelity ----------
        cos_sim = nn.functional.cosine_similarity(
            reconstructed, original_features, dim=-1
        ).mean()
        mse = nn.functional.mse_loss(reconstructed, original_features)
        fidelity = (cos_sim.clamp(min=0) * 0.7 + (1.0 - mse).clamp(min=0) * 0.3).item()

        # ---------- compression ----------
        input_dim = float(self.config.input_dim)
        target_dim = float(self.config.target_dim)
        compression_ratio = 1.0 - (target_dim / input_dim)

        # ---------- task performance ----------
        task_perf = 0.0
        if labels is not None:
            preds = task_logits.argmax(dim=-1)
            task_perf = (preds == labels).float().mean().item()

        # ---------- compose reward ----------
        w = self.config.reward_weights
        total = (
            w.get("reconstruction_fidelity", 0.4) * fidelity
            + w.get("compression_ratio", 0.3) * compression_ratio
            + w.get("embedding_usefulness", 0.2) * task_perf
            + w.get("latency", 0.1) * 1.0  # TODO: measure actual latency
        )

        reward = ChannelReward(
            fidelity=round(fidelity, 4),
            compression=round(compression_ratio, 4),
            task_performance=round(task_perf, 4),
            latency=1.0,
            total=round(total, 4),
        )

        info = {
            "cosine_similarity": round(cos_sim.item(), 4),
            "mse": round(mse.item(), 6),
            "fidelity": round(fidelity, 4),
            "compression_ratio": round(compression_ratio, 4),
            "task_accuracy": round(task_perf, 4),
            "enc_value": enc_value.mean().item(),
            "dec_value": dec_value.mean().item(),
        }

        return reward, info

    # ---------- utilities ----------

    def get_stats(self) -> dict:
        """Return channel throughput statistics."""
        s = self.stats
        avg_latency = (
            s.total_latency_ms / s.messages_sent
            if s.messages_sent > 0
            else 0.0
        )
        avg_ratio = (
            s.total_original_bytes / max(s.total_compressed_bytes, 1)
            if s.total_original_bytes > 0
            else 0.0
        )
        return {
            "messages_sent": s.messages_sent,
            "messages_received": s.messages_received,
            "avg_latency_ms": round(avg_latency, 2),
            "avg_compression_ratio": round(avg_ratio, 2),
            "total_original_bytes": s.total_original_bytes,
            "total_compressed_bytes": s.total_compressed_bytes,
        }
