"""
curriculum.py — PHIREN Curriculum Learning

5-phase training schedule (from SER1ES_VISION.md):
  Phase 0: Warmup (SL)              — supervised claim extraction
  Phase 1: Claim Extraction          — RL on extraction quality
  Phase 2: Verification Training     — NLI accuracy via RL
  Phase 3: Calibration Tuning        — confidence calibration
  Phase 4: Distillation              — adapter export
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Phase Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class PhaseConfig:
    """Configuration for a single curriculum phase."""

    phase_id: int
    name: str
    min_episodes: int                         # minimum episodes before advance
    max_episodes: int                         # force advance after this many
    lr: float                                 # learning rate
    advance_threshold: float                  # metric threshold to advance
    advance_metric: str = "factuality"        # which metric to check

    # Reward weight overrides per phase
    w_factuality: float = 0.45
    w_calibration: float = 0.25
    w_helpfulness: float = 0.20
    w_robustness: float = 0.10

    # Noise injection
    noise_rate: float = 0.0

    # Training mode
    use_supervised: bool = False               # Phase 0: SL only
    use_distillation: bool = False             # Phase 4: KD export


def default_phases() -> list[PhaseConfig]:
    """
    Default 5-phase curriculum for PHIREN training.
    """
    return [
        PhaseConfig(
            phase_id=0,
            name="Warmup (SL)",
            min_episodes=200,
            max_episodes=500,
            lr=5e-4,
            advance_threshold=0.6,
            advance_metric="claim_accuracy",
            w_factuality=0.70,
            w_calibration=0.10,
            w_helpfulness=0.15,
            w_robustness=0.05,
            noise_rate=0.0,
            use_supervised=True,
        ),
        PhaseConfig(
            phase_id=1,
            name="Claim Extraction",
            min_episodes=500,
            max_episodes=2000,
            lr=2e-4,
            advance_threshold=0.7,
            advance_metric="claim_accuracy",
            w_factuality=0.55,
            w_calibration=0.15,
            w_helpfulness=0.20,
            w_robustness=0.10,
            noise_rate=0.0,
        ),
        PhaseConfig(
            phase_id=2,
            name="Verification Training",
            min_episodes=1000,
            max_episodes=4000,
            lr=1e-4,
            advance_threshold=0.75,
            advance_metric="factuality",
            w_factuality=0.45,
            w_calibration=0.25,
            w_helpfulness=0.20,
            w_robustness=0.10,
            noise_rate=0.05,
        ),
        PhaseConfig(
            phase_id=3,
            name="Calibration Tuning",
            min_episodes=500,
            max_episodes=2000,
            lr=5e-5,
            advance_threshold=0.80,
            advance_metric="calibration",
            w_factuality=0.35,
            w_calibration=0.40,
            w_helpfulness=0.15,
            w_robustness=0.10,
            noise_rate=0.10,
        ),
        PhaseConfig(
            phase_id=4,
            name="Distillation",
            min_episodes=300,
            max_episodes=1000,
            lr=2e-5,
            advance_threshold=0.85,
            advance_metric="factuality",
            w_factuality=0.45,
            w_calibration=0.25,
            w_helpfulness=0.20,
            w_robustness=0.10,
            noise_rate=0.05,
            use_distillation=True,
        ),
    ]


# ─────────────────────────────────────────────────────────────────
#  Phase Metrics
# ─────────────────────────────────────────────────────────────────

@dataclass
class PhaseMetrics:
    """Rolling metrics for the current phase."""
    window_size: int = 100
    _rewards: deque = field(default_factory=lambda: deque(maxlen=100))
    _factuality: deque = field(default_factory=lambda: deque(maxlen=100))
    _calibration: deque = field(default_factory=lambda: deque(maxlen=100))
    _claim_accuracy: deque = field(default_factory=lambda: deque(maxlen=100))
    _success: deque = field(default_factory=lambda: deque(maxlen=100))

    def update(
        self,
        reward: float,
        factuality: float = 0.0,
        calibration: float = 0.0,
        claim_accuracy: float = 0.0,
        success: bool = False,
    ) -> None:
        self._rewards.append(reward)
        self._factuality.append(factuality)
        self._calibration.append(calibration)
        self._claim_accuracy.append(claim_accuracy)
        self._success.append(float(success))

    @property
    def avg_reward(self) -> float:
        return sum(self._rewards) / max(len(self._rewards), 1)

    @property
    def avg_factuality(self) -> float:
        return sum(self._factuality) / max(len(self._factuality), 1)

    @property
    def avg_calibration(self) -> float:
        return sum(self._calibration) / max(len(self._calibration), 1)

    @property
    def avg_claim_accuracy(self) -> float:
        return sum(self._claim_accuracy) / max(len(self._claim_accuracy), 1)

    @property
    def success_rate(self) -> float:
        return sum(self._success) / max(len(self._success), 1)

    def get_metric(self, name: str) -> float:
        return {
            "reward": self.avg_reward,
            "factuality": self.avg_factuality,
            "calibration": self.avg_calibration,
            "claim_accuracy": self.avg_claim_accuracy,
            "success_rate": self.success_rate,
        }.get(name, 0.0)

    def to_dict(self) -> dict:
        return {
            "avg_reward": round(self.avg_reward, 4),
            "avg_factuality": round(self.avg_factuality, 4),
            "avg_calibration": round(self.avg_calibration, 4),
            "avg_claim_accuracy": round(self.avg_claim_accuracy, 4),
            "success_rate": round(self.success_rate, 4),
            "samples": len(self._rewards),
        }

    def reset(self) -> None:
        self._rewards.clear()
        self._factuality.clear()
        self._calibration.clear()
        self._claim_accuracy.clear()
        self._success.clear()


# ─────────────────────────────────────────────────────────────────
#  Curriculum Scheduler
# ─────────────────────────────────────────────────────────────────

class CurriculumScheduler:
    """
    Manages phase progression during training.

    Checks metrics against phase thresholds and decides
    when to advance to the next phase.
    """

    def __init__(
        self,
        phases: Optional[list[PhaseConfig]] = None,
    ):
        self.phases = phases or default_phases()
        self.current_phase_idx = 0
        self.phase_episodes = 0
        self.total_episodes = 0
        self.metrics = PhaseMetrics()

        # Phase change callbacks
        self._on_phase_change_callbacks = []

        # History
        self._phase_history: list[dict] = []

    @property
    def current_phase(self) -> PhaseConfig:
        return self.phases[self.current_phase_idx]

    @property
    def is_final_phase(self) -> bool:
        return self.current_phase_idx >= len(self.phases) - 1

    def on_phase_change(self, callback) -> None:
        """Register a callback for phase changes."""
        self._on_phase_change_callbacks.append(callback)

    def update(
        self,
        reward: float,
        factuality: float = 0.0,
        calibration: float = 0.0,
        claim_accuracy: float = 0.0,
        success: bool = False,
    ) -> None:
        """Update metrics with latest episode result."""
        self.phase_episodes += 1
        self.total_episodes += 1
        self.metrics.update(
            reward=reward,
            factuality=factuality,
            calibration=calibration,
            claim_accuracy=claim_accuracy,
            success=success,
        )

    def should_advance(self) -> bool:
        """Check if we should advance to the next phase."""
        if self.is_final_phase:
            return False

        phase = self.current_phase

        # Must complete minimum episodes
        if self.phase_episodes < phase.min_episodes:
            return False

        # Force advance after max episodes
        if self.phase_episodes >= phase.max_episodes:
            logger.info(
                f"Phase {phase.phase_id} ({phase.name}) force-advanced "
                f"after {self.phase_episodes} episodes"
            )
            return True

        # Check metric threshold
        metric_value = self.metrics.get_metric(phase.advance_metric)
        if metric_value >= phase.advance_threshold:
            logger.info(
                f"Phase {phase.phase_id} ({phase.name}) threshold reached: "
                f"{phase.advance_metric}={metric_value:.4f} "
                f"≥ {phase.advance_threshold}"
            )
            return True

        return False

    def advance(self) -> PhaseConfig:
        """
        Advance to the next phase.

        Returns the new PhaseConfig.
        """
        old_phase = self.current_phase

        # Save history
        self._phase_history.append({
            "phase_id": old_phase.phase_id,
            "name": old_phase.name,
            "episodes": self.phase_episodes,
            "metrics": self.metrics.to_dict(),
        })

        # Advance
        self.current_phase_idx += 1
        self.phase_episodes = 0
        self.metrics.reset()

        new_phase = self.current_phase

        logger.info(
            f"╔══ Phase Change ══╗\n"
            f"  {old_phase.name} → {new_phase.name}\n"
            f"  LR: {old_phase.lr} → {new_phase.lr}\n"
            f"  Noise: {old_phase.noise_rate} → {new_phase.noise_rate}\n"
            f"╚══════════════════╝"
        )

        # Notify callbacks
        for callback in self._on_phase_change_callbacks:
            try:
                callback(old_phase, new_phase)
            except Exception as e:
                logger.error(f"Phase change callback error: {e}")

        return new_phase

    def get_state(self) -> dict:
        """Get scheduler state for checkpointing."""
        return {
            "current_phase_idx": self.current_phase_idx,
            "phase_episodes": self.phase_episodes,
            "total_episodes": self.total_episodes,
            "metrics": self.metrics.to_dict(),
            "history": self._phase_history,
        }

    def load_state(self, state: dict) -> None:
        """Restore scheduler state from checkpoint."""
        self.current_phase_idx = state.get("current_phase_idx", 0)
        self.phase_episodes = state.get("phase_episodes", 0)
        self.total_episodes = state.get("total_episodes", 0)
        self._phase_history = state.get("history", [])
        logger.info(
            f"Scheduler restored: Phase {self.current_phase_idx} "
            f"({self.current_phase.name}), episode {self.total_episodes}"
        )

    def summary(self) -> str:
        """Print curriculum summary."""
        lines = [
            "╔══════════════════════════════════════════════╗",
            "║          PHIREN Curriculum Schedule          ║",
            "╠══════════════════════════════════════════════╣",
        ]
        for i, phase in enumerate(self.phases):
            marker = " ◀" if i == self.current_phase_idx else ""
            lines.append(
                f"  Phase {phase.phase_id}: {phase.name:25s} "
                f"| LR={phase.lr:.0e} | threshold={phase.advance_threshold}{marker}"
            )
        lines.append(
            f"╠══════════════════════════════════════════════╣\n"
            f"  Current: Phase {self.current_phase_idx} "
            f"({self.current_phase.name})\n"
            f"  Episodes: {self.phase_episodes} / {self.current_phase.max_episodes}\n"
            f"  Total:    {self.total_episodes}\n"
            f"╚══════════════════════════════════════════════╝"
        )
        return "\n".join(lines)
