"""
config.py — OVISEN Training Configuration

Combines all sub-configs into a single OVisenTrainConfig.
Follows the same pattern as ogenti_train.config / phiren_train.config.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from ovisen_core.protocol import VisionProtocolConfig

logger = logging.getLogger(__name__)


@dataclass
class InfraConfig:
    """Hardware and distributed training settings."""
    num_gpus: int = 1
    gpu_memory_gb: float = 48.0
    mixed_precision: str = "bf16"
    deepspeed_stage: int = 2
    gradient_checkpointing: bool = True
    checkpoint_dir: str = "checkpoints/ovisen"
    save_every_episodes: int = 100
    keep_last_n: int = 5
    wandb_project: str = "ovisen-train"
    wandb_entity: Optional[str] = None
    log_every_episodes: int = 10
    runpod_endpoint_id: str = ""


@dataclass
class OVisenTrainConfig:
    """Master training configuration for OVISEN."""

    # Protocol
    protocol: VisionProtocolConfig = field(default_factory=VisionProtocolConfig)

    # LoRA
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: list[str] = field(
        default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj"]
    )

    # MAPPO
    ppo_clip: float = 0.2
    ppo_epochs: int = 4
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    max_grad_norm: float = 1.0
    gamma: float = 0.99
    gae_lambda: float = 0.95

    # Training
    total_episodes: int = 1000
    batch_size: int = 8
    learning_rate: float = 1e-4
    warmup_episodes: int = 50
    target_compression_ratio: float = 15.0

    # Infra
    infra: InfraConfig = field(default_factory=InfraConfig)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
        logger.info(f"Config saved to {path}")

    @classmethod
    def load(cls, path: str | Path) -> "OVisenTrainConfig":
        data = json.loads(Path(path).read_text())
        return cls(**data)
