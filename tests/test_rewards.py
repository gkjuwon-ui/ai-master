"""
test_rewards.py — Unit tests for reward functions.
"""

import pytest
from ogenti_train.rewards import (
    RewardFunction,
    RewardConfig,
    reward_accuracy,
    reward_efficiency,
    reward_clarity,
    reward_generalization,
    compute_semantic_similarity,
)


class TestSemanticSimilarity:
    def test_identical(self):
        sim = compute_semantic_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_empty(self):
        sim = compute_semantic_similarity("", "hello")
        assert sim == 0.0

    def test_partial_overlap(self):
        sim = compute_semantic_similarity(
            "the quick brown fox", "the slow brown dog"
        )
        assert 0.0 < sim < 1.0

    def test_no_overlap(self):
        sim = compute_semantic_similarity("apple banana", "car truck")
        assert sim == 0.0


class TestRewardComponents:
    def test_accuracy(self):
        acc = reward_accuracy("Paris is the capital", "Paris")
        assert acc > 0

    def test_efficiency_at_target(self):
        # Exactly at target compression → ~0.5
        eff = reward_efficiency(10, 150, target_compression=15.0)
        assert 0.4 < eff < 0.6

    def test_efficiency_high_compression(self):
        # Much better than target → approaches 1.0
        eff = reward_efficiency(5, 150, target_compression=15.0)
        assert eff > 0.7

    def test_efficiency_zero_tokens(self):
        eff = reward_efficiency(0, 150)
        assert eff == 0.0

    def test_clarity_stable(self):
        # All same accuracy → high clarity
        clarity = reward_clarity(0.8, [0.8, 0.8, 0.8, 0.8])
        assert clarity > 0.9

    def test_clarity_unstable(self):
        # Highly variable → low clarity
        clarity = reward_clarity(0.9, [0.1, 0.9, 0.1, 0.9])
        assert clarity < 0.5

    def test_generalization_equal(self):
        gen = reward_generalization(0.8, 0.8)
        assert gen == 1.0

    def test_generalization_worse(self):
        gen = reward_generalization(0.8, 0.4)
        assert gen == 0.5

    def test_generalization_zero(self):
        gen = reward_generalization(0.0, 0.5)
        assert gen == 0.0


class TestRewardFunction:
    def test_full_reward(self):
        rf = RewardFunction()
        result = rf.compute(
            decoded_text="Paris is the capital of France",
            reference="Paris",
            protocol_tokens=10,
            original_tokens=150,
            budget=30,
        )
        assert "total" in result
        assert "accuracy" in result
        assert "efficiency" in result
        assert result["protocol_tokens"] == 10

    def test_budget_violation(self):
        rf = RewardFunction()
        result = rf.compute(
            decoded_text="test",
            reference="test",
            protocol_tokens=50,
            original_tokens=150,
            budget=30,  # violated!
        )
        assert result["penalty"] < 0

    def test_empty_output_penalty(self):
        rf = RewardFunction()
        result = rf.compute(
            decoded_text="",
            reference="something",
            protocol_tokens=10,
            original_tokens=150,
            budget=30,
        )
        assert result["penalty"] < 0
