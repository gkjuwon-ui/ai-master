"""
config.py — Training Configuration

Central configuration for the entire training pipeline.
Pulls together protocol, encoder, decoder, reward, curriculum,
and infrastructure settings into a single TrainConfig.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ogenti_core.protocol import ProtocolConfig
from ogenti_train.rewards import RewardConfig
from ogenti_train.curriculum import default_phases, PhaseConfig

if TYPE_CHECKING:
    from ogenti_core.encoder import EncoderConfig
    from ogenti_core.decoder import DecoderConfig

logger = logging.getLogger(__name__)


@dataclass
class InfraConfig:
    """Infrastructure / hardware settings."""

    # Compute
    num_gpus: int = 1
    gpu_type: str = "A100-40GB"
    mixed_precision: str = "bf16"     # bf16 | fp16 | no

    # DeepSpeed
    deepspeed_stage: int = 2          # ZeRO stage (0=off, 2=recommended)
    gradient_checkpointing: bool = True

    # Checkpointing
    checkpoint_dir: str = "checkpoints"
    checkpoint_every: int = 500       # Save every N episodes
    keep_last_n: int = 3              # Rolling checkpoint window

    # Logging
    log_dir: str = "logs"
    wandb_project: str = "ogenti"
    wandb_entity: Optional[str] = None
    log_every: int = 50               # Log metrics every N episodes
    use_wandb: bool = True

    # Seed
    seed: int = 42


def _default_encoder_config():
    from ogenti_core.encoder import EncoderConfig
    return EncoderConfig()


def _default_decoder_config():
    from ogenti_core.decoder import DecoderConfig
    return DecoderConfig()


@dataclass
class TrainConfig:
    """
    Master configuration for the Ogenti training pipeline.

    Combines all sub-configs into a single serializable object.
    """

    # Sub-configs
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    encoder: any = field(default_factory=_default_encoder_config)
    decoder: any = field(default_factory=_default_decoder_config)
    reward: RewardConfig = field(default_factory=RewardConfig)
    infra: InfraConfig = field(default_factory=InfraConfig)

    # Curriculum (list of phase configs)
    phases: list[PhaseConfig] = field(default_factory=default_phases)

    # Dataset
    dataset_path: Optional[str] = None  # Path to JSONL task dataset
    eval_dataset_path: Optional[str] = None

    # Global training params
    total_episodes: int = 50000
    eval_every: int = 500
    eval_episodes: int = 100

    # Optimizer
    optimizer: str = "adamw"
    weight_decay: float = 0.01
    warmup_steps: int = 200
    lr_scheduler: str = "cosine"      # cosine | linear | constant

    def save(self, path: str) -> None:
        """Save config to JSON."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        # Custom serialization (handle non-JSON types)
        data = self._to_serializable()
        with open(p, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("Config saved to %s", path)

    @classmethod
    def load(cls, path: str) -> TrainConfig:
        """Load config from JSON."""
        with open(path) as f:
            data = json.load(f)
        return cls._from_serializable(data)

    def _to_serializable(self) -> dict:
        """Convert to a JSON-serializable dict."""
        return {
            "protocol": self.protocol.to_dict(),
            "encoder": {
                "model_name": self.encoder.model_name,
                "lora_rank": self.encoder.lora_rank,
                "lora_alpha": self.encoder.lora_alpha,
                "lora_dropout": self.encoder.lora_dropout,
                "lora_target_modules": self.encoder.lora_target_modules,
                "max_new_tokens": self.encoder.max_new_tokens,
                "encode_prefix": self.encoder.encode_prefix,
                "encode_suffix": self.encoder.encode_suffix,
            },
            "decoder": {
                "model_name": self.decoder.model_name,
                "lora_rank": self.decoder.lora_rank,
                "lora_alpha": self.decoder.lora_alpha,
                "lora_dropout": self.decoder.lora_dropout,
                "lora_target_modules": self.decoder.lora_target_modules,
                "max_decode_tokens": self.decoder.max_decode_tokens,
                "decode_prefix": self.decoder.decode_prefix,
                "decode_suffix": self.decoder.decode_suffix,
            },
            "reward": {
                "w_accuracy": self.reward.w_accuracy,
                "w_efficiency": self.reward.w_efficiency,
                "w_clarity": self.reward.w_clarity,
                "w_generalization": self.reward.w_generalization,
                "target_compression": self.reward.target_compression,
                "efficiency_scale": self.reward.efficiency_scale,
                "budget_violation_penalty": self.reward.budget_violation_penalty,
            },
            "infra": {
                "num_gpus": self.infra.num_gpus,
                "gpu_type": self.infra.gpu_type,
                "mixed_precision": self.infra.mixed_precision,
                "deepspeed_stage": self.infra.deepspeed_stage,
                "gradient_checkpointing": self.infra.gradient_checkpointing,
                "checkpoint_dir": self.infra.checkpoint_dir,
                "checkpoint_every": self.infra.checkpoint_every,
                "keep_last_n": self.infra.keep_last_n,
                "log_dir": self.infra.log_dir,
                "wandb_project": self.infra.wandb_project,
                "wandb_entity": self.infra.wandb_entity,
                "log_every": self.infra.log_every,
                "use_wandb": self.infra.use_wandb,
                "seed": self.infra.seed,
            },
            "phases": [
                {
                    "phase_id": p.phase_id,
                    "name": p.name,
                    "description": p.description,
                    "max_episodes": p.max_episodes,
                    "min_episodes": p.min_episodes,
                    "min_accuracy": p.min_accuracy,
                    "min_compression": p.min_compression,
                    "learning_rate": p.learning_rate,
                    "batch_size": p.batch_size,
                    "num_agents": p.num_agents,
                    "noise_prob": p.noise_prob,
                    "use_rl": p.use_rl,
                    "ppo_epochs": p.ppo_epochs,
                    "supervised_ratio": p.supervised_ratio,
                    "reward_weights": p.reward_weights,
                }
                for p in self.phases
            ],
            "dataset_path": self.dataset_path,
            "eval_dataset_path": self.eval_dataset_path,
            "total_episodes": self.total_episodes,
            "eval_every": self.eval_every,
            "eval_episodes": self.eval_episodes,
            "optimizer": self.optimizer,
            "weight_decay": self.weight_decay,
            "warmup_steps": self.warmup_steps,
            "lr_scheduler": self.lr_scheduler,
        }

    @classmethod
    def _from_serializable(cls, data: dict) -> TrainConfig:
        """Reconstruct from a dict."""
        from ogenti_core.encoder import EncoderConfig
        from ogenti_core.decoder import DecoderConfig

        protocol = ProtocolConfig.from_dict(data.get("protocol", {}))

        enc_data = data.get("encoder", {})
        encoder = EncoderConfig(**{
            k: v for k, v in enc_data.items()
            if k in EncoderConfig.__dataclass_fields__
        })

        dec_data = data.get("decoder", {})
        decoder = DecoderConfig(**{
            k: v for k, v in dec_data.items()
            if k in DecoderConfig.__dataclass_fields__
        })

        rew_data = data.get("reward", {})
        reward = RewardConfig(**{
            k: v for k, v in rew_data.items()
            if k in RewardConfig.__dataclass_fields__
        })

        infra_data = data.get("infra", {})
        infra = InfraConfig(**{
            k: v for k, v in infra_data.items()
            if k in InfraConfig.__dataclass_fields__
        })

        phases = [
            PhaseConfig(**p) for p in data.get("phases", [])
        ] or default_phases()

        return cls(
            protocol=protocol,
            encoder=encoder,
            decoder=decoder,
            reward=reward,
            infra=infra,
            phases=phases,
            dataset_path=data.get("dataset_path"),
            eval_dataset_path=data.get("eval_dataset_path"),
            total_episodes=data.get("total_episodes", 50000),
            eval_every=data.get("eval_every", 500),
            eval_episodes=data.get("eval_episodes", 100),
            optimizer=data.get("optimizer", "adamw"),
            weight_decay=data.get("weight_decay", 0.01),
            warmup_steps=data.get("warmup_steps", 200),
            lr_scheduler=data.get("lr_scheduler", "cosine"),
        )

    def summary(self) -> str:
        """Human-readable config summary."""
        return (
            f"═══ Ogenti Training Config ═══\n"
            f"Model:       {self.encoder.model_name}\n"
            f"LoRA rank:   {self.encoder.lora_rank}\n"
            f"Phases:      {len(self.phases)}\n"
            f"Total eps:   {self.total_episodes:,}\n"
            f"GPUs:        {self.infra.num_gpus}× {self.infra.gpu_type}\n"
            f"DeepSpeed:   ZeRO-{self.infra.deepspeed_stage}\n"
            f"Precision:   {self.infra.mixed_precision}\n"
            f"Budget:      {self.protocol.max_message_tokens} → {self.protocol.budget_floor}\n"
            f"═══════════════════════════════"
        )
