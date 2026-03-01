"""
test_curriculum.py — Unit tests for curriculum scheduler.
"""

import pytest
from ogenti_train.curriculum import (
    CurriculumScheduler,
    PhaseConfig,
    PhaseMetrics,
    default_phases,
)


class TestPhaseMetrics:
    def test_empty(self):
        m = PhaseMetrics()
        assert m.avg_accuracy == 0.0
        assert m.avg_compression == 0.0

    def test_update(self):
        m = PhaseMetrics()
        m.update(accuracy=0.8, compression=10.0, reward=0.7)
        m.update(accuracy=0.6, compression=8.0, reward=0.5)
        assert m.episodes_completed == 2
        assert m.avg_accuracy == pytest.approx(0.7)
        assert m.best_accuracy == 0.8


class TestCurriculumScheduler:
    def test_initial_phase(self):
        sched = CurriculumScheduler()
        assert sched.current_phase.phase_id == 0
        assert sched.current_phase.name == "warmup"

    def test_no_advance_before_min(self):
        phases = [
            PhaseConfig(0, "test", "", max_episodes=100, min_episodes=10,
                       min_accuracy=0.5, min_compression=2.0),
            PhaseConfig(1, "next", "", max_episodes=100),
        ]
        sched = CurriculumScheduler(phases=phases)

        # Even with great metrics, can't advance before min_episodes
        for _ in range(5):
            sched.update(accuracy=0.9, compression=20.0, reward=1.0)
        assert not sched.should_advance()

    def test_advance_on_threshold(self):
        phases = [
            PhaseConfig(0, "test", "", max_episodes=1000, min_episodes=5,
                       min_accuracy=0.7, min_compression=5.0),
            PhaseConfig(1, "next", "", max_episodes=100),
        ]
        sched = CurriculumScheduler(phases=phases)

        for _ in range(10):
            sched.update(accuracy=0.8, compression=8.0, reward=0.7)

        assert sched.should_advance()

        new_phase = sched.advance()
        assert new_phase.phase_id == 1
        assert sched.metrics.episodes_completed == 0  # Reset

    def test_force_advance_at_max(self):
        phases = [
            PhaseConfig(0, "test", "", max_episodes=5, min_episodes=0,
                       min_accuracy=0.99, min_compression=99.0),
            PhaseConfig(1, "next", "", max_episodes=100),
        ]
        sched = CurriculumScheduler(phases=phases)

        for _ in range(5):
            sched.update(accuracy=0.1, compression=1.0, reward=0.1)

        assert sched.should_advance()  # Forced by max_episodes

    def test_final_phase(self):
        sched = CurriculumScheduler()
        # Manually to final
        sched._current_phase_idx = len(sched.phases) - 1
        assert sched.is_final_phase
        assert not sched.should_advance()

    def test_history(self):
        phases = [
            PhaseConfig(0, "a", "", max_episodes=2, min_episodes=0),
            PhaseConfig(1, "b", "", max_episodes=100),
        ]
        sched = CurriculumScheduler(phases=phases)
        sched.update(0.5, 5.0, 0.4)
        sched.update(0.6, 6.0, 0.5)
        sched.advance()

        history = sched.get_history()
        assert len(history) == 1
        assert history[0]["name"] == "a"
