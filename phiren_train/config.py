"""
config.py — PHIREN Training Configuration

Combines all sub-configs into a single PhirenTrainConfig.
Follows the same pattern as ogenti_train.config.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from phiren_core.protocol import ClaimConfig
from phiren_core.detector import DetectorConfig
from phiren_core.calibrator import CalibratorConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Infrastructure Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class InfraConfig:
    """Hardware and distributed training settings."""

    # GPU
    num_gpus: int = 1
    gpu_memory_gb: float = 48.0  # per GPU
    mixed_precision: str = "bf16"  # bf16 | fp16 | no

    # DeepSpeed
    deepspeed_stage: int = 2       # 0=off, 2=ZeRO-2, 3=ZeRO-3
    gradient_checkpointing: bool = True

    # Checkpointing
    checkpoint_dir: str = "checkpoints/phiren"
    save_every_episodes: int = 100
    keep_last_n: int = 5

    # Logging
    wandb_project: str = "phiren-train"
    wandb_entity: Optional[str] = None
    log_every_episodes: int = 10

    # RunPod
    runpod_endpoint: Optional[str] = None


# ─────────────────────────────────────────────────────────────────
#  Reward Weights (from SER1ES_VISION.md)
# ─────────────────────────────────────────────────────────────────

@dataclass
class RewardWeightConfig:
    """Reward component weights."""
    w_factuality: float = 0.45
    w_calibration: float = 0.25
    w_helpfulness: float = 0.20
    w_robustness: float = 0.10

    def validate(self) -> bool:
        total = (
            self.w_factuality + self.w_calibration
            + self.w_helpfulness + self.w_robustness
        )
        return abs(total - 1.0) < 1e-6


# ─────────────────────────────────────────────────────────────────
#  Dataset Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class DatasetConfig:
    """Which hallucination datasets to use."""

    # Core datasets
    truthfulqa_path: str = "data/truthfulqa.jsonl"         # ~817 questions
    fever_path: str = "data/fever.jsonl"                   # ~185K claims
    halueval_path: str = "data/halueval.jsonl"             # ~35K examples
    phiren_combined_path: str = "data/phiren_combined.jsonl"  # ~50K curated

    # Dataset mix weights
    truthfulqa_weight: float = 0.15
    fever_weight: float = 0.35
    halueval_weight: float = 0.30
    phiren_combined_weight: float = 0.20

    # Splits
    train_ratio: float = 0.85
    val_ratio: float = 0.10
    test_ratio: float = 0.05


# ─────────────────────────────────────────────────────────────────
#  Training Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class PhirenTrainConfig:
    """
    Master configuration for PHIREN MAPPO training.

    Combines: ClaimConfig + DetectorConfig + CalibratorConfig +
    RewardWeightConfig + DatasetConfig + InfraConfig + phase params.
    """

    # Sub-configs
    claim: ClaimConfig = field(default_factory=ClaimConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    calibrator: CalibratorConfig = field(default_factory=CalibratorConfig)
    rewards: RewardWeightConfig = field(default_factory=RewardWeightConfig)
    dataset: DatasetConfig = field(default_factory=DatasetConfig)
    infra: InfraConfig = field(default_factory=InfraConfig)

    # MAPPO hyperparameters
    total_episodes: int = 10000
    episodes_per_update: int = 16       # batch size for PPO
    max_steps_per_episode: int = 5      # claim extraction + verification steps
    gamma: float = 0.99                 # discount
    gae_lambda: float = 0.95            # GAE lambda
    ppo_epochs: int = 4                 # PPO update epochs
    ppo_clip: float = 0.2              # PPO clip range
    entropy_coef: float = 0.01         # entropy bonus
    value_loss_coef: float = 0.5       # critic loss weight
    max_grad_norm: float = 1.0         # gradient clipping

    # Learning rates (overridden per phase by curriculum)
    lr_detector: float = 2e-4
    lr_verifier: float = 2e-4
    lr_critic: float = 1e-3

    # Phase settings (defaults — overridden by curriculum.py)
    num_phases: int = 5
    phase_names: list[str] = field(default_factory=lambda: [
        "Warmup (SL)",
        "Claim Extraction",
        "Verification Training",
        "Calibration Tuning",
        "Distillation",
    ])

    # Monitor server
    monitor_port: int = 8765

    def save(self, path: str) -> None:
        """Save config to JSON."""
        filepath = Path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Custom serialization for nested dataclasses
        data = {
            "claim": self.claim.to_dict(),
            "detector": self.detector.to_dict(),
            "calibrator": self.calibrator.to_dict(),
            "rewards": asdict(self.rewards),
            "dataset": asdict(self.dataset),
            "infra": asdict(self.infra),
            "total_episodes": self.total_episodes,
            "episodes_per_update": self.episodes_per_update,
            "max_steps_per_episode": self.max_steps_per_episode,
            "gamma": self.gamma,
            "gae_lambda": self.gae_lambda,
            "ppo_epochs": self.ppo_epochs,
            "ppo_clip": self.ppo_clip,
            "entropy_coef": self.entropy_coef,
            "value_loss_coef": self.value_loss_coef,
            "max_grad_norm": self.max_grad_norm,
            "lr_detector": self.lr_detector,
            "lr_verifier": self.lr_verifier,
            "lr_critic": self.lr_critic,
            "num_phases": self.num_phases,
            "phase_names": self.phase_names,
            "monitor_port": self.monitor_port,
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Config saved to {filepath}")

    @classmethod
    def load(cls, path: str) -> PhirenTrainConfig:
        """Load config from JSON."""
        with open(path) as f:
            data = json.load(f)

        config = cls()

        if "claim" in data:
            config.claim = ClaimConfig.from_dict(data["claim"])
        if "detector" in data:
            for k, v in data["detector"].items():
                if hasattr(config.detector, k):
                    setattr(config.detector, k, v)
        if "calibrator" in data:
            for k, v in data["calibrator"].items():
                if hasattr(config.calibrator, k):
                    setattr(config.calibrator, k, v)
        if "rewards" in data:
            for k, v in data["rewards"].items():
                if hasattr(config.rewards, k):
                    setattr(config.rewards, k, v)
        if "dataset" in data:
            for k, v in data["dataset"].items():
                if hasattr(config.dataset, k):
                    setattr(config.dataset, k, v)
        if "infra" in data:
            for k, v in data["infra"].items():
                if hasattr(config.infra, k):
                    setattr(config.infra, k, v)

        # Top-level params
        for key in [
            "total_episodes", "episodes_per_update", "max_steps_per_episode",
            "gamma", "gae_lambda", "ppo_epochs", "ppo_clip",
            "entropy_coef", "value_loss_coef", "max_grad_norm",
            "lr_detector", "lr_verifier", "lr_critic",
            "num_phases", "phase_names", "monitor_port",
        ]:
            if key in data:
                setattr(config, key, data[key])

        logger.info(f"Config loaded from {path}")
        return config

    def summary(self) -> str:
        """Print a human-readable summary."""
        lines = [
            "╔══════════════════════════════════════════════╗",
            "║          PHIREN Training Config              ║",
            "╠══════════════════════════════════════════════╣",
            f"  Backbone:       {self.detector.model_name}",
            f"  NLI Model:      {self.detector.nli_model_name}",
            f"  LoRA r:         {self.detector.lora_r}",
            f"  Episodes:       {self.total_episodes}",
            f"  Batch Size:     {self.episodes_per_update}",
            f"  PPO Clip:       {self.ppo_clip}",
            f"  LR (detector):  {self.lr_detector}",
            f"  LR (verifier):  {self.lr_verifier}",
            "╠══════════════════════════════════════════════╣",
            "║  Reward Weights                              ║",
            f"  Factuality:     {self.rewards.w_factuality}",
            f"  Calibration:    {self.rewards.w_calibration}",
            f"  Helpfulness:    {self.rewards.w_helpfulness}",
            f"  Robustness:     {self.rewards.w_robustness}",
            "╠══════════════════════════════════════════════╣",
            "║  Infrastructure                             ║",
            f"  GPUs:           {self.infra.num_gpus}",
            f"  DeepSpeed:      Stage {self.infra.deepspeed_stage}",
            f"  Mixed Precision:{self.infra.mixed_precision}",
            f"  Checkpoint:     {self.infra.checkpoint_dir}",
            "╚══════════════════════════════════════════════╝",
        ]
        return "\n".join(lines)
