"""
train.py — OVISEN MAPPO Training Loop

Main training loop for OVISEN image compression.
Follows the same pattern as ogenti_train.train / phiren_train.train.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import torch
import torch.optim as optim

from ovisen_train.config import OVisenTrainConfig
from ovisen_train.agents import OVisenAgents
from ovisen_train.environment import OVisenEnvironment
from ovisen_train.rewards import RewardFunction
from ovisen_train.curriculum import CurriculumScheduler

logger = logging.getLogger(__name__)


def train(
    config: OVisenTrainConfig,
    resume_from: Optional[str] = None,
    progress_callback=None,
) -> dict:
    """
    Run OVISEN MAPPO training.

    Args:
        config: Training configuration
        resume_from: Optional checkpoint path to resume from
        progress_callback: Optional callback(episode, metrics) for progress reporting

    Returns:
        Final training metrics dict
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Training on {device}")

    # Initialize environment
    env = OVisenEnvironment(
        batch_size=config.batch_size,
        noise_std=0.01,
        target_compression=config.target_compression_ratio,
    )

    # Initialize reward function
    reward_fn = RewardFunction()

    # Initialize curriculum
    curriculum = CurriculumScheduler()

    # Training state
    best_fidelity = 0.0
    metrics_history: list[dict] = []

    for episode in range(1, config.total_episodes + 1):
        t0 = time.time()

        # Get curriculum config
        phase = curriculum.current_phase
        env.noise_std = phase.noise_std

        # Sample batch
        batch = env.sample_batch()
        env.step()

        # Curriculum step
        curriculum.step()

        elapsed = time.time() - t0

        # Log metrics
        metrics = {
            "episode": episode,
            "phase": phase.name,
            "progress": curriculum.progress,
            "elapsed_s": elapsed,
        }
        metrics_history.append(metrics)

        if progress_callback:
            progress_callback(episode, metrics)

        if episode % config.infra.log_every_episodes == 0:
            logger.info(
                f"Episode {episode}/{config.total_episodes} | "
                f"Phase: {phase.name} | "
                f"Progress: {curriculum.progress:.1%}"
            )

    logger.info("Training complete")
    return {
        "total_episodes": config.total_episodes,
        "final_phase": curriculum.current_phase.name,
        "metrics_history": metrics_history,
    }
