"""
ogenti-train — MARL Training Pipeline for Ogenti Protocol

Modules:
  environment  — Task generation & environment loop
  agents       — MARL agent wrappers (encoder/decoder + value head)
  rewards      — Multi-component reward function
  curriculum   — 4-phase curriculum scheduler
  config       — Central training configuration
  train        — Main MAPPO training loop
"""

__version__ = "0.1.0"

# Light imports (no torch dependency)
from ogenti_train.environment import (
    OgentiEnvironment,
    TaskGenerator,
    Task,
    TaskCategory,
    EpisodeResult,
)
from ogenti_train.rewards import RewardFunction, RewardConfig
from ogenti_train.curriculum import CurriculumScheduler, PhaseConfig, PhaseMetrics


def __getattr__(name):
    """Lazy imports for torch-dependent modules."""
    if name in ("TrainConfig", "InfraConfig"):
        from ogenti_train.config import TrainConfig, InfraConfig
        return {"TrainConfig": TrainConfig, "InfraConfig": InfraConfig}[name]
    if name in ("AgentPool", "EncoderAgent", "DecoderAgent", "ValueHead",
                "AgentConfig", "RolloutBuffer"):
        from ogenti_train import agents as _agents
        return getattr(_agents, name)
    if name == "OgentiTrainer":
        from ogenti_train.train import OgentiTrainer
        return OgentiTrainer
    raise AttributeError(f"module 'ogenti_train' has no attribute {name!r}")


__all__ = [
    "TrainConfig",
    "InfraConfig",
    "OgentiEnvironment",
    "TaskGenerator",
    "Task",
    "TaskCategory",
    "EpisodeResult",
    "AgentPool",
    "EncoderAgent",
    "DecoderAgent",
    "ValueHead",
    "AgentConfig",
    "RolloutBuffer",
    "RewardFunction",
    "RewardConfig",
    "CurriculumScheduler",
    "PhaseConfig",
    "PhaseMetrics",
    "OgentiTrainer",
]
