"""
telepathy_rewards.py — Reward Functions for Telepathy v2 Training

v1 reward: R = w_acc * accuracy + w_eff * compression + w_cla * clarity + w_gen * generalization
v2 reward: R = w_task * task_success + w_intent * intent_match + w_eff * efficiency + w_comp * composability
           + VICReg regularization + uniformity bonus + collapse penalty + noise robustness bonus

Key differences from v1:
  - No more "compression ratio" — there are no tokens to compress
  - "task_success" replaces "accuracy" — measured by downstream task completion
  - "intent_match" — did the receiver correctly classify the sender's intent?
  - "composability" — can SES vectors be composed (added/interpolated) meaningfully?
  - VICReg + uniformity prevent embedding collapse (main failure mode)
  - Cross-model & cross-modal bonuses encourage universal SES
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn.functional as F

from ogenti_core.telepathy import (
    TelepathyConfig,
    TELEPATHY_CONFIG,
    Intent,
    vicreg_loss,
    uniformity_loss,
    compute_effective_dimensionality,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#                  REWARD CONFIGURATION
# ═══════════════════════════════════════════════════════════════

@dataclass
class TelepathyRewardConfig:
    """Reward weights for Telepathy v2 training.

    Design doc Section 3.3:
      w_task_success   = 0.50  (downstream task completion)
      w_intent_match   = 0.20  (intent classification accuracy)
      w_efficiency     = 0.15  (message size / communication overhead)
      w_composability  = 0.15  (SES vector arithmetic works)
    """
    # Primary weights (sum to 1.0)
    w_task_success: float = 0.50
    w_intent_match: float = 0.20
    w_efficiency: float = 0.15
    w_composability: float = 0.15

    # Regularization weights
    vicreg_weight: float = 0.10       # VICReg loss multiplier
    uniformity_weight: float = 0.05   # Uniformity loss multiplier

    # Penalties
    collapse_penalty: float = -2.0    # Applied when effective_dim < threshold
    noise_sensitivity_penalty: float = -0.5  # Applied when noise degrades >50%

    # Bonuses
    cross_model_bonus: float = 0.3    # Bonus when sender/receiver are different LLMs
    cross_modal_bonus: float = 0.5    # Bonus when text→image or image→text works

    # Thresholds
    collapse_dim_threshold: float = 0.3
    noise_degrade_threshold: float = 0.5


# ═══════════════════════════════════════════════════════════════
#                  REWARD COMPONENTS
# ═══════════════════════════════════════════════════════════════

def reward_task_success(
    receiver_output: str,
    reference: str,
    method: str = "token_overlap",
) -> float:
    """R_task: Did the receiver produce the correct output after receiving the SES vector?

    Range: [0, 1]
    """
    from ogenti_train.rewards import compute_semantic_similarity
    return compute_semantic_similarity(receiver_output, reference, method)


def reward_intent_match(
    predicted_intent: int,
    true_intent: int,
) -> float:
    """R_intent: Did the receiver correctly classify the sender's intent?

    Binary: 1.0 if correct, 0.0 if wrong.
    """
    return 1.0 if predicted_intent == true_intent else 0.0


def reward_efficiency(
    message_bytes: int,
    baseline_tokens: int,
    bytes_per_token: float = 4.0,
) -> float:
    """R_efficiency: How compact is the SES message vs. token-based protocol?

    Compares SES message size to what v1 token protocol would have used.
    A 512-dim float16 SES vector = 1040 bytes ≈ 260 protocol tokens.
    But it conveys MORE information (continuous vs. discrete).

    We measure efficiency as: 1 - (message_bytes / baseline_bytes)
    High efficiency = SES message much smaller than token-based equivalent.
    """
    baseline_bytes = baseline_tokens * bytes_per_token
    if baseline_bytes <= 0:
        return 0.0
    ratio = message_bytes / baseline_bytes
    # Sigmoid-shaped curve: very efficient → 1.0, same as baseline → 0.5
    return 1.0 / (1.0 + math.exp(2 * (ratio - 1.0)))


def reward_composability(
    vec_a: torch.Tensor,
    vec_b: torch.Tensor,
    vec_ab: torch.Tensor,
    composed: torch.Tensor,
) -> float:
    """R_composability: Do SES vector arithmetic operations work?

    Tests: vec("A and B") ≈ (vec("A") + vec("B")) / 2
    This is the "king - man + woman ≈ queen" test for our SES.

    Args:
        vec_a: SES vector for concept A
        vec_b: SES vector for concept B
        vec_ab: SES vector for combined concept "A and B"
        composed: (vec_a + vec_b) normalized — the predicted composition

    Returns:
        Cosine similarity between vec_ab and composed. Range: [-1, 1] → clamped [0, 1]
    """
    sim = F.cosine_similarity(vec_ab.unsqueeze(0), composed.unsqueeze(0)).item()
    return max(0.0, sim)


def reward_noise_robustness(
    clean_similarity: float,
    noisy_similarity: float,
) -> float:
    """R_noise: How robust is the SES vector to noise?

    Tests: Does task_success degrade when noise is added to the SES vector?
    Slight degradation is OK, but >50% degradation is penalized.

    Args:
        clean_similarity: task_success with clean SES vector
        noisy_similarity: task_success with noisy SES vector (σ=0.01)
    """
    if clean_similarity < 0.01:
        return 0.0
    retention = noisy_similarity / clean_similarity
    return min(1.0, retention)


# ═══════════════════════════════════════════════════════════════
#                  COMPOSITE REWARD FUNCTION
# ═══════════════════════════════════════════════════════════════

class TelepathyRewardFunction:
    """Composite reward function for Telepathy v2 MARL training."""

    def __init__(self, config: Optional[TelepathyRewardConfig] = None):
        self.config = config or TelepathyRewardConfig()
        self.recent_effective_dims: list[float] = []

    def compute(
        self,
        *,
        # Task success
        receiver_output: str,
        reference: str,
        # Intent
        predicted_intent: int,
        true_intent: int,
        # Efficiency
        message_bytes: int,
        baseline_tokens: int,
        # SES vectors (for regularization)
        ses_vectors_a: Optional[torch.Tensor] = None,
        ses_vectors_b: Optional[torch.Tensor] = None,
        # Composability
        vec_a: Optional[torch.Tensor] = None,
        vec_b: Optional[torch.Tensor] = None,
        vec_ab: Optional[torch.Tensor] = None,
        # Noise robustness
        noisy_output: Optional[str] = None,
        # Cross-model/modal flags
        is_cross_model: bool = False,
        is_cross_modal: bool = False,
    ) -> dict:
        """Compute full reward with all components.

        Returns dict with:
          - total_reward: float
          - components: dict[str, float] (individual component values)
          - penalties: dict[str, float]
          - bonuses: dict[str, float]
          - regularization: dict[str, float]
        """
        cfg = self.config
        components = {}
        penalties = {}
        bonuses = {}
        regularization = {}

        # ── Primary Components ──────────────────────────────────
        task_r = reward_task_success(receiver_output, reference)
        components["task_success"] = task_r

        intent_r = reward_intent_match(predicted_intent, true_intent)
        components["intent_match"] = intent_r

        eff_r = reward_efficiency(message_bytes, baseline_tokens)
        components["efficiency"] = eff_r

        # Composability (optional)
        comp_r = 0.0
        if vec_a is not None and vec_b is not None and vec_ab is not None:
            composed = F.normalize(vec_a + vec_b, dim=-1)
            comp_r = reward_composability(vec_a, vec_b, vec_ab, composed)
        components["composability"] = comp_r

        # ── Weighted Sum ────────────────────────────────────────
        total = (
            cfg.w_task_success * task_r
            + cfg.w_intent_match * intent_r
            + cfg.w_efficiency * eff_r
            + cfg.w_composability * comp_r
        )

        # ── Regularization ──────────────────────────────────────
        if ses_vectors_a is not None and ses_vectors_b is not None:
            vic = vicreg_loss(ses_vectors_a, ses_vectors_b)
            reg_value = cfg.vicreg_weight * vic.item()
            regularization["vicreg"] = reg_value
            total -= reg_value  # Subtract penalty

            uni = uniformity_loss(ses_vectors_a)
            uni_value = cfg.uniformity_weight * uni.item()
            regularization["uniformity"] = uni_value
            total -= uni_value  # More uniform = higher reward (uni is negative when good)

        # ── Collapse Detection ──────────────────────────────────
        if ses_vectors_a is not None and ses_vectors_a.size(0) >= 10:
            eff_dim = compute_effective_dimensionality(ses_vectors_a)
            self.recent_effective_dims.append(eff_dim)
            if len(self.recent_effective_dims) > 50:
                self.recent_effective_dims.pop(0)

            if eff_dim < cfg.collapse_dim_threshold:
                penalties["collapse"] = cfg.collapse_penalty
                total += cfg.collapse_penalty
                logger.warning(
                    "SES collapse detected! effective_dim=%.3f (threshold=%.3f)",
                    eff_dim, cfg.collapse_dim_threshold,
                )

        # ── Noise Robustness ────────────────────────────────────
        if noisy_output is not None:
            noisy_sim = reward_task_success(noisy_output, reference)
            noise_r = reward_noise_robustness(task_r, noisy_sim)
            if noise_r < cfg.noise_degrade_threshold:
                penalties["noise_sensitivity"] = cfg.noise_sensitivity_penalty
                total += cfg.noise_sensitivity_penalty

        # ── Bonuses ─────────────────────────────────────────────
        if is_cross_model and task_r > 0.5:
            bonuses["cross_model"] = cfg.cross_model_bonus
            total += cfg.cross_model_bonus

        if is_cross_modal and task_r > 0.3:
            bonuses["cross_modal"] = cfg.cross_modal_bonus
            total += cfg.cross_modal_bonus

        return {
            "total_reward": total,
            "components": components,
            "penalties": penalties,
            "bonuses": bonuses,
            "regularization": regularization,
        }

    def compute_contrastive_reward(
        self,
        ses_vectors_a: torch.Tensor,
        ses_vectors_b: torch.Tensor,
        tau: float = 0.07,
    ) -> torch.Tensor:
        """InfoNCE contrastive loss as a training signal for Phase 0 alignment.

        This is used as a loss (minimize), not a reward.
        Lower = better alignment between paired views.
        """
        from ogenti_core.telepathy import contrastive_loss
        return contrastive_loss(ses_vectors_a, ses_vectors_b, tau=tau)
