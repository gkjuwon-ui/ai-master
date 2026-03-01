"""
curriculum.py — Curriculum Learning Scheduler

Manages the 4-phase training progression:

  Phase 0: Warmup        — Supervised pretraining, no RL
  Phase 1: Simple 1:1    — Single encoder-decoder pairs, MARL begins
  Phase 2: Complex       — Multi-hop relay chains, 3+ agents
  Phase 3: Generalize    — Zero-shot on unseen task categories

Phase transitions are triggered by performance thresholds
(accuracy, compression ratio) or by episode count.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Phase Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class PhaseConfig:
    """Configuration for a single training phase."""

    phase_id: int
    name: str
    description: str

    # Duration
    max_episodes: int
    min_episodes: int = 0    # Must run at least this many before promotion

    # Promotion thresholds (all must be met)
    min_accuracy: float = 0.0
    min_compression: float = 0.0

    # Training params
    learning_rate: float = 1e-4
    batch_size: int = 16
    num_agents: int = 2
    noise_prob: float = 0.0
    token_budget: Optional[int] = None  # Override protocol config if set

    # RL params
    use_rl: bool = True
    ppo_epochs: int = 4
    supervised_ratio: float = 0.0  # Fraction of supervised loss mixed in

    # Reward weight adjustments
    reward_weights: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────
#  Default Phase Configs (from OGENTI_SYSTEM_DESIGN.md)
# ─────────────────────────────────────────────────────────────────

def default_phases() -> list[PhaseConfig]:
    """Return the 4 default training phases."""
    return [
        PhaseConfig(
            phase_id=0,
            name="warmup",
            description="Supervised pretraining — teach basic encoding/decoding",
            max_episodes=5000,
            min_episodes=2000,
            min_accuracy=0.6,
            min_compression=2.0,
            learning_rate=5e-4,
            batch_size=32,
            num_agents=2,
            noise_prob=0.0,
            use_rl=False,
            supervised_ratio=1.0,
            ppo_epochs=0,
            reward_weights={
                "w_accuracy": 0.8,
                "w_efficiency": 0.1,
                "w_clarity": 0.1,
                "w_generalization": 0.0,
            },
        ),
        PhaseConfig(
            phase_id=1,
            name="simple",
            description="Simple 1:1 communication — MARL kicks in",
            max_episodes=15000,
            min_episodes=5000,
            min_accuracy=0.75,
            min_compression=8.0,
            learning_rate=2e-4,
            batch_size=16,
            num_agents=2,
            noise_prob=0.05,
            use_rl=True,
            supervised_ratio=0.3,
            ppo_epochs=4,
            reward_weights={
                "w_accuracy": 0.45,
                "w_efficiency": 0.30,
                "w_clarity": 0.15,
                "w_generalization": 0.10,
            },
        ),
        PhaseConfig(
            phase_id=2,
            name="complex",
            description="Multi-hop relay chains — 3+ agents",
            max_episodes=20000,
            min_episodes=8000,
            min_accuracy=0.70,
            min_compression=12.0,
            learning_rate=1e-4,
            batch_size=8,
            num_agents=3,
            noise_prob=0.10,
            use_rl=True,
            supervised_ratio=0.1,
            ppo_epochs=4,
            reward_weights={
                "w_accuracy": 0.40,
                "w_efficiency": 0.30,
                "w_clarity": 0.20,
                "w_generalization": 0.10,
            },
        ),
        PhaseConfig(
            phase_id=3,
            name="generalize",
            description="Zero-shot generalization — unseen task categories",
            max_episodes=10000,
            min_episodes=3000,
            min_accuracy=0.65,
            min_compression=15.0,
            learning_rate=5e-5,
            batch_size=8,
            num_agents=2,
            noise_prob=0.15,
            use_rl=True,
            supervised_ratio=0.0,
            ppo_epochs=6,
            reward_weights={
                "w_accuracy": 0.35,
                "w_efficiency": 0.25,
                "w_clarity": 0.15,
                "w_generalization": 0.25,
            },
        ),
    ]


# ─────────────────────────────────────────────────────────────────
#  Performance Tracker
# ─────────────────────────────────────────────────────────────────

@dataclass
class PhaseMetrics:
    """Rolling metrics for the current phase."""

    episodes_completed: int = 0
    total_accuracy: float = 0.0
    total_compression: float = 0.0
    total_reward: float = 0.0
    best_accuracy: float = 0.0
    best_compression: float = 0.0

    @property
    def avg_accuracy(self) -> float:
        if self.episodes_completed == 0:
            return 0.0
        return self.total_accuracy / self.episodes_completed

    @property
    def avg_compression(self) -> float:
        if self.episodes_completed == 0:
            return 0.0
        return self.total_compression / self.episodes_completed

    @property
    def avg_reward(self) -> float:
        if self.episodes_completed == 0:
            return 0.0
        return self.total_reward / self.episodes_completed

    def update(self, accuracy: float, compression: float, reward: float) -> None:
        self.episodes_completed += 1
        self.total_accuracy += accuracy
        self.total_compression += compression
        self.total_reward += reward
        self.best_accuracy = max(self.best_accuracy, accuracy)
        self.best_compression = max(self.best_compression, compression)

    def summary(self) -> dict:
        return {
            "episodes": self.episodes_completed,
            "avg_accuracy": f"{self.avg_accuracy:.4f}",
            "avg_compression": f"{self.avg_compression:.1f}x",
            "avg_reward": f"{self.avg_reward:.4f}",
            "best_accuracy": f"{self.best_accuracy:.4f}",
            "best_compression": f"{self.best_compression:.1f}x",
        }


# ─────────────────────────────────────────────────────────────────
#  Curriculum Scheduler
# ─────────────────────────────────────────────────────────────────

class CurriculumScheduler:
    """
    Manages phase transitions based on performance metrics.

    Usage
    -----
    >>> scheduler = CurriculumScheduler()
    >>> phase_cfg = scheduler.current_phase
    >>> # ... train for one episode ...
    >>> scheduler.update(accuracy=0.8, compression=10.0, reward=0.7)
    >>> if scheduler.should_advance():
    ...     scheduler.advance()
    """

    def __init__(
        self,
        phases: Optional[list[PhaseConfig]] = None,
        on_phase_change: Optional[Callable[[int, PhaseConfig], None]] = None,
    ):
        self.phases = phases or default_phases()
        self.on_phase_change = on_phase_change
        self._current_phase_idx = 0
        self._metrics = PhaseMetrics()
        self._phase_history: list[dict] = []

    @property
    def current_phase(self) -> PhaseConfig:
        return self.phases[self._current_phase_idx]

    @property
    def current_phase_idx(self) -> int:
        return self._current_phase_idx

    @property
    def metrics(self) -> PhaseMetrics:
        return self._metrics

    @property
    def is_final_phase(self) -> bool:
        return self._current_phase_idx >= len(self.phases) - 1

    @property
    def is_training_complete(self) -> bool:
        """Training is done when final phase hits max_episodes or thresholds."""
        if not self.is_final_phase:
            return False
        phase = self.current_phase
        return (
            self._metrics.episodes_completed >= phase.max_episodes
            or (
                self._metrics.episodes_completed >= phase.min_episodes
                and self._meets_thresholds()
            )
        )

    def update(
        self,
        accuracy: float,
        compression: float,
        reward: float,
    ) -> None:
        """Record metrics from the latest episode."""
        self._metrics.update(accuracy, compression, reward)

    def should_advance(self) -> bool:
        """Check if the current phase should advance to the next."""
        if self.is_final_phase:
            return False

        phase = self.current_phase
        met = self._metrics

        # Must complete minimum episodes
        if met.episodes_completed < phase.min_episodes:
            return False

        # Hit max episodes → force advance
        if met.episodes_completed >= phase.max_episodes:
            logger.info(
                "Phase %d (%s) hit max episodes (%d), advancing",
                phase.phase_id, phase.name, phase.max_episodes,
            )
            return True

        # Check performance thresholds
        if self._meets_thresholds():
            logger.info(
                "Phase %d (%s) met thresholds (acc=%.3f, comp=%.1fx), advancing",
                phase.phase_id, phase.name,
                met.avg_accuracy, met.avg_compression,
            )
            return True

        return False

    def advance(self) -> PhaseConfig:
        """Advance to the next phase."""
        old = self.current_phase

        # Save phase history
        self._phase_history.append({
            "phase": old.phase_id,
            "name": old.name,
            **self._metrics.summary(),
        })

        # Move to next phase
        self._current_phase_idx += 1
        self._metrics = PhaseMetrics()

        new = self.current_phase
        logger.info(
            "═══ Phase transition: %s → %s ═══",
            old.name, new.name,
        )

        if self.on_phase_change:
            self.on_phase_change(new.phase_id, new)

        return new

    def get_history(self) -> list[dict]:
        """Get the full phase transition history."""
        return list(self._phase_history)

    def _meets_thresholds(self) -> bool:
        """Check if current metrics meet phase promotion thresholds."""
        phase = self.current_phase
        met = self._metrics
        return (
            met.avg_accuracy >= phase.min_accuracy
            and met.avg_compression >= phase.min_compression
        )

    def __repr__(self) -> str:
        phase = self.current_phase
        return (
            f"CurriculumScheduler(phase={phase.phase_id}/{len(self.phases)-1} "
            f"'{phase.name}', ep={self._metrics.episodes_completed})"
        )
