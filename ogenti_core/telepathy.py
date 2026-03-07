"""
O-Series Telepathy v2 — Core Modules

TextProjector:    LLM hidden state → SES vector (zero-latency thought projection)
VisionProjector:  ViT CLS embedding → SES vector (cross-modal telepathy)
InjectionHead:    SES vector → virtual hidden states (thought injection into LLM)
TelepathyMessage: Binary message format for SES vector transmission
"""

import struct
import hashlib
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np


# ═══════════════════════════════════════════════════════════════
#                  TELEPATHY CONFIGURATION
# ═══════════════════════════════════════════════════════════════

class Intent(IntEnum):
    QUERY = 0
    INSTRUCT = 1
    REPORT = 2
    NEGOTIATE = 3


class Modality(IntEnum):
    TEXT = 0
    IMAGE = 1
    STRUCTURED = 2
    MULTIMODAL = 3


class TelepathyFlags(IntEnum):
    HAS_CONTEXT = 1 << 0
    MULTI_VECTOR = 1 << 1
    STREAMING = 1 << 2
    COMPRESSED_INT8 = 1 << 3


@dataclass
class TelepathyConfig:
    """Central configuration for the Telepathy v2 system."""
    # SES dimensions
    ses_dim: int = 512
    # Number of virtual tokens injected into receiver LLM
    n_virtual_tokens: int = 4
    # Number of intent categories
    num_intents: int = 4
    # Contrastive learning temperature
    contrastive_tau: float = 0.07
    # VICReg weights (anti-collapse)
    vicreg_variance_weight: float = 25.0
    vicreg_covariance_weight: float = 1.0
    vicreg_invariance_weight: float = 25.0
    # Uniformity loss weight
    uniformity_weight: float = 0.5
    # Collapse detection threshold
    collapse_threshold: float = 0.3  # effective_dim / ses_dim
    # Noise sensitivity test level
    noise_test_level: float = 0.01
    # Supported LLM hidden sizes (for projector auto-config)
    supported_hidden_sizes: list = field(default_factory=lambda: [
        768, 1024, 1536, 2048, 2560, 3072, 3584, 4096, 5120, 6144, 8192
    ])
    # Message format
    magic: bytes = b"TPY\x01"
    version: int = 2

    def get_nearest_hidden_size(self, actual_size: int) -> int:
        """Snap to nearest supported hidden size."""
        return min(self.supported_hidden_sizes, key=lambda s: abs(s - actual_size))


TELEPATHY_CONFIG = TelepathyConfig()


# ═══════════════════════════════════════════════════════════════
#                  TEXT PROJECTOR (OGENTI v2)
# ═══════════════════════════════════════════════════════════════

class TextProjector(nn.Module):
    """Projects LLM hidden states into the Shared Embedding Space (SES).

    v1: hidden → token logits → sample tokens → transmit (500ms+)
    v2: hidden → SES vector → transmit (<1ms)

    The entire autoregressive generation step is eliminated.
    """

    def __init__(self, llm_dim: int = 2048, ses_dim: int = 512, num_intents: int = 4):
        super().__init__()
        self.llm_dim = llm_dim
        self.ses_dim = ses_dim

        self.project = nn.Sequential(
            nn.Linear(llm_dim, llm_dim),
            nn.GELU(),
            nn.LayerNorm(llm_dim),
            nn.Linear(llm_dim, ses_dim),
            nn.LayerNorm(ses_dim),
        )
        # Auxiliary intent classification head
        self.intent_head = nn.Linear(ses_dim, num_intents)

    def forward(self, hidden_state: torch.Tensor, pool: str = "mean") -> torch.Tensor:
        """
        Args:
            hidden_state: [batch, seq_len, llm_dim] — last layer output from LLM
            pool: pooling strategy — "mean", "last", or "cls"

        Returns:
            ses_vector: [batch, ses_dim] — L2-normalized SES embedding
        """
        if hidden_state.dim() == 3:
            if pool == "mean":
                pooled = hidden_state.mean(dim=1)
            elif pool == "last":
                pooled = hidden_state[:, -1, :]
            elif pool == "cls":
                pooled = hidden_state[:, 0, :]
            else:
                pooled = hidden_state.mean(dim=1)
        else:
            pooled = hidden_state

        ses_vector = self.project(pooled)
        ses_vector = F.normalize(ses_vector, dim=-1)
        return ses_vector

    def classify_intent(self, ses_vector: torch.Tensor) -> torch.Tensor:
        """Classify the intent of a SES vector. Returns logits [batch, num_intents]."""
        return self.intent_head(ses_vector)


# ═══════════════════════════════════════════════════════════════
#                VISION PROJECTOR (OVISEN v2)
# ═══════════════════════════════════════════════════════════════

class VisionProjector(nn.Module):
    """Projects ViT embeddings into the same SES space as text.

    v1 OVISEN: ViT [CLS] → 256-dim private space (separate from OGENTI)
    v2 OVISEN: ViT [CLS] → 512-dim SES space (same space as text!)

    This enables cross-modal telepathy: image ↔ text in one space.
    """

    def __init__(self, vit_dim: int = 768, ses_dim: int = 512):
        super().__init__()
        self.vit_dim = vit_dim
        self.ses_dim = ses_dim

        self.project = nn.Sequential(
            nn.Linear(vit_dim, vit_dim),
            nn.GELU(),
            nn.LayerNorm(vit_dim),
            nn.Linear(vit_dim, ses_dim),
            nn.LayerNorm(ses_dim),
        )

    def forward(self, cls_embedding: torch.Tensor) -> torch.Tensor:
        """
        Args:
            cls_embedding: [batch, vit_dim] — ViT [CLS] token embedding

        Returns:
            ses_vector: [batch, ses_dim] — L2-normalized SES embedding
        """
        ses_vector = self.project(cls_embedding)
        ses_vector = F.normalize(ses_vector, dim=-1)
        return ses_vector


# ═══════════════════════════════════════════════════════════════
#               INJECTION HEAD (Receiver Side)
# ═══════════════════════════════════════════════════════════════

class InjectionHead(nn.Module):
    """Converts SES vectors back into LLM-compatible hidden states.

    Instead of tokenizing text and running a prefill pass (50ms+),
    we directly inject virtual tokens into the LLM's KV cache.

    Think of it like implanting a memory directly into the brain.
    """

    def __init__(self, ses_dim: int = 512, llm_dim: int = 2048, n_virtual_tokens: int = 4):
        super().__init__()
        self.ses_dim = ses_dim
        self.llm_dim = llm_dim
        self.n_virtual_tokens = n_virtual_tokens

        self.expand = nn.Sequential(
            nn.Linear(ses_dim, llm_dim * n_virtual_tokens),
            nn.GELU(),
        )
        self.layer_norm = nn.LayerNorm(llm_dim)

    def forward(self, ses_vector: torch.Tensor) -> torch.Tensor:
        """
        Args:
            ses_vector: [batch, ses_dim]

        Returns:
            virtual_hidden: [batch, n_virtual_tokens, llm_dim]
            These get prepended to the LLM's input embeddings sequence.
        """
        expanded = self.expand(ses_vector)  # [batch, llm_dim * N]
        reshaped = expanded.view(
            ses_vector.size(0),
            self.n_virtual_tokens,
            self.llm_dim,
        )
        return self.layer_norm(reshaped)


# ═══════════════════════════════════════════════════════════════
#            ADAPTIVE INPUT PROJECTION (Multi-Model)
# ═══════════════════════════════════════════════════════════════

class AdaptiveProjector(nn.Module):
    """Auto-adapts to any LLM's hidden dimension.

    Maintains separate Linear layers for known hidden sizes (2048, 3072, 4096, etc.)
    so one adapter can work with Qwen (2048), Llama (3072/4096), Mistral (4096), etc.
    """

    def __init__(self, ses_dim: int = 512, supported_sizes: Optional[list] = None):
        super().__init__()
        sizes = supported_sizes or TELEPATHY_CONFIG.supported_hidden_sizes
        self.projectors = nn.ModuleDict({
            str(s): TextProjector(llm_dim=s, ses_dim=ses_dim)
            for s in sizes
        })
        self.injectors = nn.ModuleDict({
            str(s): InjectionHead(ses_dim=ses_dim, llm_dim=s)
            for s in sizes
        })
        self.ses_dim = ses_dim

    def get_projector(self, hidden_size: int) -> TextProjector:
        key = str(TELEPATHY_CONFIG.get_nearest_hidden_size(hidden_size))
        if key not in self.projectors:
            raise ValueError(f"Unsupported hidden size: {hidden_size}")
        return self.projectors[key]

    def get_injector(self, hidden_size: int) -> InjectionHead:
        key = str(TELEPATHY_CONFIG.get_nearest_hidden_size(hidden_size))
        if key not in self.injectors:
            raise ValueError(f"Unsupported hidden size: {hidden_size}")
        return self.injectors[key]


# ═══════════════════════════════════════════════════════════════
#                  SES REGULARIZATION LOSSES
# ═══════════════════════════════════════════════════════════════

def vicreg_loss(
    z_a: torch.Tensor,
    z_b: torch.Tensor,
    config: TelepathyConfig = TELEPATHY_CONFIG,
) -> torch.Tensor:
    """VICReg (Variance-Invariance-Covariance) loss to prevent embedding collapse.

    Args:
        z_a: [batch, ses_dim] — SES vectors from view A (e.g. text)
        z_b: [batch, ses_dim] — SES vectors from view B (e.g. same text paraphrased, or matching image)
    """
    batch_size, dim = z_a.shape

    # 1. Invariance: matched pairs should be close
    inv_loss = F.mse_loss(z_a, z_b)

    # 2. Variance: each dimension should have variance > 1
    std_a = z_a.std(dim=0)
    std_b = z_b.std(dim=0)
    var_loss = (
        F.relu(1.0 - std_a).mean() +
        F.relu(1.0 - std_b).mean()
    )

    # 3. Covariance: dimensions should be decorrelated
    z_a_centered = z_a - z_a.mean(dim=0)
    z_b_centered = z_b - z_b.mean(dim=0)
    cov_a = (z_a_centered.T @ z_a_centered) / (batch_size - 1)
    cov_b = (z_b_centered.T @ z_b_centered) / (batch_size - 1)
    # Zero out diagonal (we only penalize off-diagonal)
    mask = ~torch.eye(dim, dtype=torch.bool, device=cov_a.device)
    cov_loss = (cov_a[mask].pow(2).mean() + cov_b[mask].pow(2).mean())

    return (
        config.vicreg_invariance_weight * inv_loss
        + config.vicreg_variance_weight * var_loss
        + config.vicreg_covariance_weight * cov_loss
    )


def uniformity_loss(z: torch.Tensor) -> torch.Tensor:
    """Encourages SES vectors to be uniformly distributed on the hypersphere.

    L_uniform = log(E[exp(-2 * ||z_i - z_j||^2)])
    """
    sq_pdist = torch.cdist(z, z, p=2).pow(2)
    # Exclude self-distances (diagonal)
    mask = ~torch.eye(z.size(0), dtype=torch.bool, device=z.device)
    return sq_pdist[mask].mul(-2).exp().mean().log()


def contrastive_loss(
    z_a: torch.Tensor,
    z_b: torch.Tensor,
    tau: float = 0.07,
) -> torch.Tensor:
    """InfoNCE contrastive loss (CLIP-style).

    Pulls matching (text, image) pairs together, pushes non-matching apart.
    Used in Phase 0 (SES Alignment).
    """
    # Cosine similarity matrix
    logits = (z_a @ z_b.T) / tau  # [batch, batch]
    labels = torch.arange(z_a.size(0), device=z_a.device)
    loss_a = F.cross_entropy(logits, labels)
    loss_b = F.cross_entropy(logits.T, labels)
    return (loss_a + loss_b) / 2


def compute_effective_dimensionality(z: torch.Tensor) -> float:
    """Measures how many dimensions of SES are actually being used.

    Uses PCA explained variance ratio. If embeddings collapse to a
    low-dimensional subspace, this number drops.

    Returns: fraction of effective dimensions (0.0 to 1.0)
    """
    z_centered = z - z.mean(dim=0)
    # Covariance matrix
    cov = (z_centered.T @ z_centered) / (z.size(0) - 1)
    eigenvalues = torch.linalg.eigvalsh(cov)
    eigenvalues = eigenvalues.clamp(min=0)
    # Normalize to probabilities
    total = eigenvalues.sum()
    if total < 1e-8:
        return 0.0
    probs = eigenvalues / total
    # Shannon entropy as effective dimensionality
    entropy = -(probs * (probs + 1e-10).log()).sum()
    max_entropy = torch.tensor(float(z.size(1))).log()
    return (entropy / max_entropy).item()


# ═══════════════════════════════════════════════════════════════
#                  TELEPATHY MESSAGE FORMAT
# ═══════════════════════════════════════════════════════════════

MAGIC = b"TPY\x01"
HEADER_FORMAT = "!4sBHB"  # magic(4) + version(1) + ses_dim(2) + flags(1) = 8 bytes
META_FORMAT = "!BBB5s"    # intent(1) + modality(1) + urgency(1) + reserved(5) = 8 bytes
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
META_SIZE = struct.calcsize(META_FORMAT)


@dataclass
class TelepathyMessage:
    """Binary message for SES vector transmission.

    Total size: 16 (header+meta) + ses_dim*2 (float16 payload) bytes
    For ses_dim=512: 16 + 1024 = 1040 bytes ≈ 1KB
    """
    ses_vector: np.ndarray       # float16, shape (ses_dim,)
    intent: Intent = Intent.INSTRUCT
    modality: Modality = Modality.TEXT
    urgency: int = 128
    flags: int = 0
    sender_id: str = ""
    receiver_id: str = ""

    @property
    def ses_dim(self) -> int:
        return self.ses_vector.shape[0]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()[:16]

    def to_bytes(self) -> bytes:
        """Serialize to binary wire format."""
        header = struct.pack(HEADER_FORMAT, MAGIC, TELEPATHY_CONFIG.version, self.ses_dim, self.flags)
        meta = struct.pack(META_FORMAT, self.intent, self.modality, self.urgency, b"\x00" * 5)
        payload = self.ses_vector.astype(np.float16).tobytes()
        return header + meta + payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "TelepathyMessage":
        """Deserialize from binary wire format."""
        magic, version, ses_dim, flags = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
        if magic != MAGIC:
            raise ValueError(f"Invalid magic: {magic!r}")
        intent, modality, urgency, _ = struct.unpack(META_FORMAT, data[HEADER_SIZE:HEADER_SIZE + META_SIZE])
        payload_start = HEADER_SIZE + META_SIZE
        vec = np.frombuffer(data[payload_start:payload_start + ses_dim * 2], dtype=np.float16).copy()
        return cls(ses_vector=vec, intent=Intent(intent), modality=Modality(modality), urgency=urgency, flags=flags)

    def to_tensor(self, device: str = "cpu") -> torch.Tensor:
        """Convert SES vector to torch tensor."""
        return torch.from_numpy(self.ses_vector.astype(np.float32)).to(device)

    @classmethod
    def from_tensor(
        cls,
        tensor: torch.Tensor,
        intent: Intent = Intent.INSTRUCT,
        modality: Modality = Modality.TEXT,
    ) -> "TelepathyMessage":
        """Create message from a torch SES vector."""
        vec = tensor.detach().cpu().float().numpy().astype(np.float16)
        return cls(ses_vector=vec, intent=intent, modality=modality)

    @property
    def size_bytes(self) -> int:
        return HEADER_SIZE + META_SIZE + self.ses_dim * 2

    def __repr__(self) -> str:
        return (
            f"TelepathyMessage(dim={self.ses_dim}, intent={self.intent.name}, "
            f"modality={self.modality.name}, size={self.size_bytes}B, "
            f"fp={self.fingerprint})"
        )


# ═══════════════════════════════════════════════════════════════
#                  TELEPATHY CHANNEL
# ═══════════════════════════════════════════════════════════════

@dataclass
class TelepathyStats:
    """Runtime statistics for telepathy communication."""
    messages_sent: int = 0
    total_bytes: int = 0
    avg_cosine_fidelity: float = 0.0
    noise_injections: int = 0
    cross_model_transfers: int = 0
    cross_modal_transfers: int = 0
    collapse_warnings: int = 0

    @property
    def avg_message_size(self) -> float:
        return self.total_bytes / max(self.messages_sent, 1)


class TelepathyChannel:
    """Communication channel for SES vector transmission.

    Handles routing, noise injection (for robustness training),
    and fidelity monitoring.
    """

    def __init__(self, config: TelepathyConfig = TELEPATHY_CONFIG, noise_std: float = 0.0):
        self.config = config
        self.noise_std = noise_std
        self.stats = TelepathyStats()
        self._agents: dict[str, callable] = {}
        self._recent_vectors: list[torch.Tensor] = []

    def register(self, agent_id: str, callback: callable):
        self._agents[agent_id] = callback

    def unregister(self, agent_id: str):
        self._agents.pop(agent_id, None)

    def send(self, message: TelepathyMessage, original_hidden: Optional[torch.Tensor] = None) -> bool:
        """Send a TelepathyMessage to the receiver."""
        if message.receiver_id not in self._agents:
            return False

        vec_tensor = message.to_tensor()

        # Inject noise during training for robustness
        if self.noise_std > 0:
            noise = torch.randn_like(vec_tensor) * self.noise_std
            vec_tensor = F.normalize(vec_tensor + noise, dim=-1)
            message = TelepathyMessage.from_tensor(vec_tensor, message.intent, message.modality)
            message.receiver_id = message.receiver_id  # preserve
            self.stats.noise_injections += 1

        # Track for collapse detection
        self._recent_vectors.append(vec_tensor.detach())
        if len(self._recent_vectors) > 100:
            self._recent_vectors.pop(0)

        # Deliver
        self._agents[message.receiver_id](message)
        self.stats.messages_sent += 1
        self.stats.total_bytes += message.size_bytes

        return True

    def check_collapse(self) -> float:
        """Check if SES vectors are collapsing to a low-dimensional subspace."""
        if len(self._recent_vectors) < 10:
            return 1.0
        z = torch.stack(self._recent_vectors[-50:])
        eff_dim = compute_effective_dimensionality(z)
        if eff_dim < self.config.collapse_threshold:
            self.stats.collapse_warnings += 1
        return eff_dim

    def reset_stats(self):
        self.stats = TelepathyStats()
        self._recent_vectors.clear()
