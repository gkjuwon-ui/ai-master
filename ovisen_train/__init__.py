"""
ovisen_train — MARL Training Pipeline for Ovisen Image Compression

Modules:
  environment  — Image dataset loading & environment loop
  agents       — MARL agent wrappers (encoder/decoder + value head)
  rewards      — Multi-component reward (fidelity + compression + clarity + generalization)
  curriculum   — 4-phase curriculum scheduler
  config       — Central training configuration
  train        — Main MAPPO training loop
  server       — RunPod worker server
"""

__version__ = "0.1.0"

from ovisen_train.config import OVisenTrainConfig, InfraConfig
from ovisen_train.rewards import RewardFunction, RewardConfig
from ovisen_train.curriculum import CurriculumScheduler


def __getattr__(name):
    """Lazy imports for torch-dependent modules."""
    if name == "OVisenAgents":
        from ovisen_train.agents import OVisenAgents
        return OVisenAgents
    if name == "OVisenEnvironment":
        from ovisen_train.environment import OVisenEnvironment
        return OVisenEnvironment
    raise AttributeError(f"module 'ovisen_train' has no attribute {name}")
