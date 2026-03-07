"""
telepathy_adapter.py — Telepathy v2 Universal Adapter

The .ogt v2 adapter packages:
  1. TextProjector   (hidden → SES vector)
  2. VisionProjector (ViT CLS → SES vector)
  3. InjectionHead   (SES vector → virtual tokens)
  4. SES calibration data (mean/std from training)

One adapter works with ANY LLM — Qwen, Llama, Mistral, Phi, etc.
via AdaptiveProjector (per-hidden-size projection layers).

Size: ~5-6MB (vs. 2GB+ for LoRA adapters).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from ogenti_core.telepathy import (
    TelepathyConfig,
    TELEPATHY_CONFIG,
    TextProjector,
    VisionProjector,
    InjectionHead,
    AdaptiveProjector,
    TelepathyMessage,
    TelepathyChannel,
    Intent,
    Modality,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#                  ADAPTER CONFIGURATION
# ═══════════════════════════════════════════════════════════════

@dataclass
class TelepathyAdapterConfig:
    """Serializable metadata for a saved .ogt v2 adapter."""
    version: str = "2.0"
    ses_dim: int = 512
    n_virtual_tokens: int = 4
    num_intents: int = 4
    trained_on: str = "Qwen/Qwen2.5-3B-Instruct"
    training_episodes: int = 0
    has_vision: bool = True
    supported_hidden_sizes: list = None
    contrastive_tau: float = 0.07

    def __post_init__(self):
        if self.supported_hidden_sizes is None:
            self.supported_hidden_sizes = TELEPATHY_CONFIG.supported_hidden_sizes

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TelepathyAdapterConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════
#                  SES CALIBRATION DATA
# ═══════════════════════════════════════════════════════════════

@dataclass
class SESCalibration:
    """Calibration statistics from training. Used for normalization."""
    mean: np.ndarray        # [ses_dim] mean of all training SES vectors
    std: np.ndarray         # [ses_dim] std per dimension
    effective_dim: float    # measured effective dimensionality (0-1)
    n_samples: int          # number of vectors used for calibration

    def save(self, path: Path):
        np.savez(path, mean=self.mean, std=self.std,
                 effective_dim=self.effective_dim, n_samples=self.n_samples)

    @classmethod
    def load(cls, path: Path) -> "SESCalibration":
        data = np.load(path)
        return cls(
            mean=data["mean"],
            std=data["std"],
            effective_dim=float(data["effective_dim"]),
            n_samples=int(data["n_samples"]),
        )

    @classmethod
    def from_vectors(cls, vectors: torch.Tensor) -> "SESCalibration":
        """Compute calibration from a batch of SES vectors."""
        v = vectors.detach().cpu().float().numpy()
        return cls(
            mean=v.mean(axis=0),
            std=v.std(axis=0),
            effective_dim=0.0,  # computed separately
            n_samples=v.shape[0],
        )


# ═══════════════════════════════════════════════════════════════
#                  TELEPATHY ADAPTER (v2)
# ═══════════════════════════════════════════════════════════════

class TelepathyAdapter(nn.Module):
    """
    Universal telepathy adapter — the .ogt v2 file.

    v1 OgentiAdapter: PPH + PRH → token-level protocol (token compression)
    v2 TelepathyAdapter: TextProjector + VisionProjector + InjectionHead → SES telepathy

    Usage:
        adapter = TelepathyAdapter.load("path/to/adapter")
        adapter.attach(model, tokenizer)

        # Send thought
        msg = adapter.send("Summarize this document")

        # Receive thought
        virtual_tokens = adapter.receive(msg)
    """

    def __init__(
        self,
        config: Optional[TelepathyAdapterConfig] = None,
        use_adaptive: bool = True,
    ):
        super().__init__()
        self.config = config or TelepathyAdapterConfig()
        self.calibration: Optional[SESCalibration] = None

        if use_adaptive:
            self.adaptive = AdaptiveProjector(
                ses_dim=self.config.ses_dim,
                supported_sizes=self.config.supported_hidden_sizes,
            )
            self._text_projector = None
            self._injection_head = None
        else:
            self.adaptive = None
            self._text_projector = TextProjector(
                llm_dim=2048, ses_dim=self.config.ses_dim,
                num_intents=self.config.num_intents,
            )
            self._injection_head = InjectionHead(
                ses_dim=self.config.ses_dim, llm_dim=2048,
                n_virtual_tokens=self.config.n_virtual_tokens,
            )

        # Vision projector (shared across all model sizes — ViT dim is fixed)
        self.vision_projector = VisionProjector(
            vit_dim=768, ses_dim=self.config.ses_dim,
        ) if self.config.has_vision else None

        # Attached model state
        self._model = None
        self._tokenizer = None
        self._model_hidden_size: Optional[int] = None

    def get_text_projector(self) -> TextProjector:
        if self.adaptive and self._model_hidden_size:
            return self.adaptive.get_projector(self._model_hidden_size)
        if self._text_projector:
            return self._text_projector
        raise RuntimeError("No model attached and no default projector set")

    def get_injection_head(self) -> InjectionHead:
        if self.adaptive and self._model_hidden_size:
            return self.adaptive.get_injector(self._model_hidden_size)
        if self._injection_head:
            return self._injection_head
        raise RuntimeError("No model attached and no default injector set")

    # ── Attach / Detach ────────────────────────────────────────

    def attach(self, model, tokenizer) -> "TelepathyAdapter":
        """Attach the adapter to an LLM for sending/receiving."""
        self._model = model
        self._tokenizer = tokenizer

        if hasattr(model.config, "hidden_size"):
            self._model_hidden_size = model.config.hidden_size
        elif hasattr(model.config, "d_model"):
            self._model_hidden_size = model.config.d_model
        else:
            raise ValueError("Cannot detect model hidden size.")

        logger.info(
            "TelepathyAdapter v2 attached to %s (hidden_size=%d)",
            type(model).__name__, self._model_hidden_size,
        )
        return self

    def detach(self):
        self._model = None
        self._tokenizer = None
        self._model_hidden_size = None

    # ── Send (Encode → SES → Message) ─────────────────────────

    def send(
        self,
        text: str,
        intent: Intent = Intent.INSTRUCT,
        pool: str = "mean",
    ) -> TelepathyMessage:
        """Encode natural language into a TelepathyMessage via SES projection.

        v1: text → tokenize → LLM forward → LoRA → autoregressive token gen (500ms)
        v2: text → tokenize → LLM forward → TextProjector → SES vector (<1ms)
        """
        if self._model is None:
            raise RuntimeError("No model attached. Call adapter.attach(model, tokenizer) first.")

        inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs, output_hidden_states=True)
            hidden = outputs.hidden_states[-1]  # [1, seq, hidden_dim]

        projector = self.get_text_projector()
        ses_vector = projector(hidden, pool=pool)  # [1, ses_dim]

        # Classify intent from the SES vector
        intent_logits = projector.classify_intent(ses_vector)
        detected_intent = Intent(intent_logits.argmax(dim=-1).item())

        msg = TelepathyMessage.from_tensor(
            ses_vector.squeeze(0),
            intent=detected_intent,
            modality=Modality.TEXT,
        )
        return msg

    def send_vision(self, cls_embedding: torch.Tensor) -> TelepathyMessage:
        """Encode a ViT [CLS] embedding into a TelepathyMessage."""
        if self.vision_projector is None:
            raise RuntimeError("Vision projector not available")
        ses_vector = self.vision_projector(cls_embedding)
        return TelepathyMessage.from_tensor(ses_vector.squeeze(0), modality=Modality.IMAGE)

    # ── Receive (Message → SES → Virtual Tokens) ──────────────

    def receive(self, message: TelepathyMessage) -> torch.Tensor:
        """Decode a TelepathyMessage into virtual hidden states for the receiver LLM.

        v1: protocol tokens → PRH → hidden states → generate (50ms+)
        v2: SES vector → InjectionHead → virtual_tokens → prepend to input (sub-ms)
        """
        device = "cpu"
        if self._model is not None:
            device = next(self._model.parameters()).device

        ses_tensor = message.to_tensor(device).unsqueeze(0)  # [1, ses_dim]
        injector = self.get_injection_head()
        virtual_hidden = injector(ses_tensor)  # [1, n_virtual_tokens, llm_dim]
        return virtual_hidden

    def receive_and_generate(
        self,
        message: TelepathyMessage,
        max_new_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        """Receive a telepathy message and generate a response."""
        if self._model is None:
            raise RuntimeError("No model attached.")

        virtual_hidden = self.receive(message)  # [1, N, llm_dim]

        output_ids = self._model.generate(
            inputs_embeds=virtual_hidden,
            max_new_tokens=max_new_tokens,
            do_sample=temperature > 0,
            temperature=max(temperature, 1e-4),
            pad_token_id=self._tokenizer.eos_token_id,
        )
        return self._tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()

    # ── Training Helpers ───────────────────────────────────────

    def project_for_training(
        self,
        hidden_states: torch.Tensor,
        pool: str = "mean",
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Project hidden states and return (ses_vector, intent_logits).
        Used during training to compute losses.
        """
        projector = self.get_text_projector()
        ses = projector(hidden_states, pool=pool)
        intent_logits = projector.classify_intent(ses)
        return ses, intent_logits

    def inject_for_training(self, ses_vector: torch.Tensor) -> torch.Tensor:
        """Inject SES vector → virtual tokens. Used during training."""
        injector = self.get_injection_head()
        return injector(ses_vector)

    # ── Save / Load ────────────────────────────────────────────

    def save(self, save_dir: Union[str, Path]) -> None:
        """Export the Telepathy v2 adapter.

        Creates:
          save_dir/
            telepathy_config.json
            projector_weights.pt / .safetensors
            vision_weights.pt (optional)
            injector_weights.pt
            ses_calibration.npz (optional)
        """
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Config
        (save_dir / "telepathy_config.json").write_text(
            json.dumps(self.config.to_dict(), indent=2)
        )

        # Weights
        try:
            from safetensors.torch import save_file
            save_fn = lambda sd, path: save_file(sd, str(path))
            ext = ".safetensors"
        except ImportError:
            save_fn = torch.save
            ext = ".pt"

        if self.adaptive:
            save_fn(self.adaptive.state_dict(), save_dir / f"adaptive_weights{ext}")
        else:
            if self._text_projector:
                save_fn(self._text_projector.state_dict(), save_dir / f"projector_weights{ext}")
            if self._injection_head:
                save_fn(self._injection_head.state_dict(), save_dir / f"injector_weights{ext}")

        if self.vision_projector:
            save_fn(self.vision_projector.state_dict(), save_dir / f"vision_weights{ext}")

        # Calibration
        if self.calibration:
            self.calibration.save(save_dir / "ses_calibration.npz")

        logger.info("TelepathyAdapter v2 saved to %s", save_dir)

    @classmethod
    def load(cls, load_dir: Union[str, Path]) -> "TelepathyAdapter":
        """Load a Telepathy v2 adapter from a saved directory."""
        load_dir = Path(load_dir)

        config = TelepathyAdapterConfig.from_dict(
            json.loads((load_dir / "telepathy_config.json").read_text())
        )

        # Determine weight format
        has_st = (load_dir / "adaptive_weights.safetensors").exists()

        adapter = cls(config=config, use_adaptive=(load_dir / f"adaptive_weights{'.safetensors' if has_st else '.pt'}").exists())

        try:
            from safetensors.torch import load_file
            load_fn = load_file
        except ImportError:
            load_fn = lambda p: torch.load(p, weights_only=True)

        # Load weights
        for name, pattern in [
            ("adaptive", "adaptive_weights"),
            ("_text_projector", "projector_weights"),
            ("_injection_head", "injector_weights"),
            ("vision_projector", "vision_weights"),
        ]:
            for ext in (".safetensors", ".pt"):
                path = load_dir / f"{pattern}{ext}"
                if path.exists():
                    module = getattr(adapter, name, None)
                    if module is not None:
                        module.load_state_dict(load_fn(str(path)))
                    break

        # Calibration
        cal_path = load_dir / "ses_calibration.npz"
        if cal_path.exists():
            adapter.calibration = SESCalibration.load(cal_path)

        logger.info("TelepathyAdapter v2 loaded from %s", load_dir)
        return adapter

    # ── Info ───────────────────────────────────────────────────

    def param_count(self) -> dict:
        """Return parameter counts for each component."""
        counts = {}
        if self.adaptive:
            counts["adaptive_projectors"] = sum(p.numel() for p in self.adaptive.projectors.parameters())
            counts["adaptive_injectors"] = sum(p.numel() for p in self.adaptive.injectors.parameters())
        if self._text_projector:
            counts["text_projector"] = sum(p.numel() for p in self._text_projector.parameters())
        if self._injection_head:
            counts["injection_head"] = sum(p.numel() for p in self._injection_head.parameters())
        if self.vision_projector:
            counts["vision_projector"] = sum(p.numel() for p in self.vision_projector.parameters())
        counts["total"] = sum(counts.values())
        return counts

    def size_mb(self) -> float:
        """Approximate adapter size in MB (float32)."""
        total_params = sum(p.numel() for p in self.parameters())
        return total_params * 4 / (1024 * 1024)

    def __repr__(self) -> str:
        parts = [f"TelepathyAdapter(v{self.config.version}, ses_dim={self.config.ses_dim}"]
        if self._model_hidden_size:
            parts.append(f", attached={self._model_hidden_size}d")
        parts.append(f", size={self.size_mb():.1f}MB)")
        return "".join(parts)
