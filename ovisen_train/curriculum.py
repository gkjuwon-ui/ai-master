"""
curriculum.py — OVISEN Curriculum Scheduler

4-phase training curriculum:
  Phase 1: Simple images, low compression target
  Phase 2: Complex images, standard compression
  Phase 3: Mixed categories, high compression
  Phase 4: Adversarial noise, maximum compression
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PhaseConfig:
    """Configuration for a curriculum phase."""
    name: str
    episodes: int
    noise_std: float
    target_compression: float
    min_fidelity: float
    categories: list[str] = field(default_factory=lambda: ["natural"])


class CurriculumScheduler:
    """Manages phase transitions during training."""

    def __init__(self, phases: list[PhaseConfig] | None = None):
        self.phases = phases or default_phases()
        self._current_phase = 0
        self._episode_in_phase = 0

    @property
    def current_phase(self) -> PhaseConfig:
        return self.phases[min(self._current_phase, len(self.phases) - 1)]

    @property
    def phase_index(self) -> int:
        return self._current_phase

    def step(self, metrics: dict | None = None) -> bool:
        """Advance one episode. Returns True if phase changed."""
        self._episode_in_phase += 1

        if self._episode_in_phase >= self.current_phase.episodes:
            if self._current_phase < len(self.phases) - 1:
                self._current_phase += 1
                self._episode_in_phase = 0
                logger.info(f"Phase transition → {self.current_phase.name}")
                return True
        return False

    @property
    def progress(self) -> float:
        """Overall progress 0.0 → 1.0."""
        total = sum(p.episodes for p in self.phases)
        done = sum(p.episodes for p in self.phases[:self._current_phase])
        done += self._episode_in_phase
        return min(1.0, done / max(total, 1))


def default_phases() -> list[PhaseConfig]:
    return [
        PhaseConfig(
            name="basic_compression",
            episodes=200,
            noise_std=0.0,
            target_compression=5.0,
            min_fidelity=0.8,
            categories=["natural"],
        ),
        PhaseConfig(
            name="standard_compression",
            episodes=300,
            noise_std=0.01,
            target_compression=10.0,
            min_fidelity=0.75,
            categories=["natural", "synthetic"],
        ),
        PhaseConfig(
            name="high_compression",
            episodes=300,
            noise_std=0.02,
            target_compression=15.0,
            min_fidelity=0.7,
            categories=["natural", "synthetic", "medical", "satellite"],
        ),
        PhaseConfig(
            name="adversarial",
            episodes=200,
            noise_std=0.05,
            target_compression=20.0,
            min_fidelity=0.65,
            categories=["natural", "synthetic", "medical", "satellite", "document", "art"],
        ),
    ]
