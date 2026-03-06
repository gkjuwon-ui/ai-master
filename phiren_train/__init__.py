"""
phiren_train — PHIREN MAPPO Training Module

Multi-Agent Proximal Policy Optimization for hallucination detection.

Agents:
  - DetectorAgent: learns to extract claims and run NLI
  - VerifierAgent: learns to calibrate confidence and produce verdicts

Rewards (from SER1ES_VISION.md):
  - Factuality:   0.45 — correct verdicts
  - Calibration:  0.25 — well-calibrated confidence
  - Helpfulness:  0.20 — useful explanations
  - Robustness:   0.10 — noise-invariant
"""

from .config import PhirenTrainConfig, InfraConfig
from .rewards import RewardFunction, RewardConfig
from .agents import DetectorAgent, VerifierAgent, AgentPool
from .environment import PhirenEnvironment, TaskGenerator
from .curriculum import CurriculumScheduler, PhaseConfig, default_phases
from .train import PhirenTrainer
from .server import PhirenTrainerBridge, create_app, start_server

__all__ = [
    "PhirenTrainConfig",
    "InfraConfig",
    "RewardFunction",
    "RewardConfig",
    "DetectorAgent",
    "VerifierAgent",
    "AgentPool",
    "PhirenEnvironment",
    "TaskGenerator",
    "CurriculumScheduler",
    "PhaseConfig",
    "default_phases",
    "PhirenTrainer",
    "PhirenTrainerBridge",
    "create_app",
    "start_server",
]

__version__ = "0.1.0"
