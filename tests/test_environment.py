"""
test_environment.py — Unit tests for task environment.
"""

import pytest
from ogenti_train.environment import (
    OgentiEnvironment,
    TaskGenerator,
    Task,
    TaskCategory,
    PHASE_CATEGORIES,
)


class TestTaskGenerator:
    def test_synthetic_generation(self):
        gen = TaskGenerator(phase=0)
        assert len(gen) > 0

    def test_sample(self):
        gen = TaskGenerator(phase=0, seed=42)
        tasks = gen.sample(3)
        assert len(tasks) == 3
        for t in tasks:
            assert isinstance(t, Task)
            assert t.instruction

    def test_phase_filtering(self):
        gen = TaskGenerator(phase=0, seed=42)
        allowed = set(PHASE_CATEGORIES[0])
        tasks = gen.sample(10)
        for t in tasks:
            assert t.category in allowed

    def test_phase_change(self):
        gen = TaskGenerator(phase=0)
        gen.set_phase(3)
        tasks = gen.sample(5)
        assert len(tasks) == 5


class TestTask:
    def test_serialization(self):
        task = Task(
            task_id="test_1",
            category=TaskCategory.SUMMARIZE,
            instruction="Summarize this",
            reference="Summary",
            difficulty=0.5,
        )
        d = task.to_dict()
        restored = Task.from_dict(d)
        assert restored.task_id == "test_1"
        assert restored.category == TaskCategory.SUMMARIZE


class TestOgentiEnvironment:
    def test_reset(self):
        env = OgentiEnvironment()
        task = env.reset()
        assert isinstance(task, Task)
        assert env.current_task is task

    def test_step(self):
        env = OgentiEnvironment()
        env.reset()
        result = env.step("decoded output")
        assert result.decoded_text == "decoded output"
        assert result.episode_num == 0

    def test_episode_increment(self):
        env = OgentiEnvironment()
        env.reset()
        env.step("a")
        env.reset()
        env.step("b")
        assert env.episode == 2
