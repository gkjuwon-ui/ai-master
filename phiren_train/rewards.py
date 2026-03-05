"""
rewards.py — PHIREN Reward Functions

Multi-component reward for hallucination detection MAPPO training.

Weights (SERIES_VISION.md):
  - Factuality:   0.45 — correct claim verdicts vs ground truth
  - Calibration:  0.25 — confidence matches actual accuracy
  - Helpfulness:  0.20 — informative verdicts, no over-filtering
  - Robustness:   0.10 — stable under noise / adversarial inputs
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from phiren_core.protocol import (
    Claim,
    ClaimVerdict,
    VerificationMessage,
    compute_ece,
    compute_factuality_score,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Reward Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class RewardConfig:
    """Reward hyperparameters."""

    # Component weights
    w_factuality: float = 0.45
    w_calibration: float = 0.25
    w_helpfulness: float = 0.20
    w_robustness: float = 0.10

    # Factuality
    correct_verdict_bonus: float = 1.0
    wrong_verdict_penalty: float = -1.0

    # Calibration
    ece_penalty_scale: float = 2.0       # penalty = -scale * ECE

    # Helpfulness
    supported_bonus: float = 0.1         # bonus for correctly supporting valid claims
    over_filter_penalty: float = -0.3    # penalty for marking valid claims as contradicted
    miss_penalty: float = -0.5           # penalty for missing actual hallucinations

    # Robustness
    noise_stability_bonus: float = 0.5   # bonus if verdict unchanged under noise
    noise_flip_penalty: float = -0.3     # penalty if verdict changes under noise

    # Clipping
    min_reward: float = -2.0
    max_reward: float = 2.0


# ─────────────────────────────────────────────────────────────────
#  Individual Reward Functions
# ─────────────────────────────────────────────────────────────────

def reward_factuality(
    predicted: list[Claim],
    ground_truth: list[dict],
    config: RewardConfig,
) -> float:
    """
    Factuality reward: did the detector get the verdicts right?

    ground_truth: list of {"claim_text": str, "verdict": str}
    """
    if not predicted or not ground_truth:
        return 0.0

    # Build ground truth lookup
    gt_map = {}
    for gt in ground_truth:
        gt_map[gt.get("claim_text", "").lower().strip()] = gt.get("verdict", "supported")

    total_score = 0.0
    matched = 0

    for claim in predicted:
        claim_text = claim.text.lower().strip()

        # Try exact match first, then fuzzy
        gt_verdict = gt_map.get(claim_text)
        if gt_verdict is None:
            # Fuzzy match — find closest ground truth
            gt_verdict = _find_closest_gt(claim_text, gt_map)

        if gt_verdict is None:
            continue  # no match found

        matched += 1
        if claim.verdict and claim.verdict.value == gt_verdict:
            total_score += config.correct_verdict_bonus
        else:
            total_score += config.wrong_verdict_penalty

    if matched == 0:
        return 0.0
    return total_score / matched


def _find_closest_gt(claim: str, gt_map: dict[str, str]) -> Optional[str]:
    """Find the closest ground truth claim via token overlap."""
    claim_tokens = set(claim.split())
    best_score = 0.0
    best_verdict = None

    for gt_text, gt_verdict in gt_map.items():
        gt_tokens = set(gt_text.split())
        if not gt_tokens:
            continue
        overlap = len(claim_tokens & gt_tokens) / max(len(claim_tokens | gt_tokens), 1)
        if overlap > best_score and overlap > 0.5:  # minimum 50% overlap
            best_score = overlap
            best_verdict = gt_verdict

    return best_verdict


def reward_calibration(
    predicted: list[Claim],
    ground_truth: list[dict],
    config: RewardConfig,
) -> float:
    """
    Calibration reward: is confidence well-calibrated?

    High reward when confidence matches actual accuracy.
    """
    if not predicted:
        return 0.0

    gt_map = {}
    for gt in ground_truth:
        gt_map[gt.get("claim_text", "").lower().strip()] = gt.get("verdict", "supported")

    confidences = []
    accuracies = []

    for claim in predicted:
        if claim.verdict is None:
            continue

        claim_text = claim.text.lower().strip()
        gt_verdict = gt_map.get(claim_text)
        if gt_verdict is None:
            gt_verdict = _find_closest_gt(claim_text, gt_map)
        if gt_verdict is None:
            continue

        confidences.append(claim.confidence)
        is_correct = 1.0 if claim.verdict.value == gt_verdict else 0.0
        accuracies.append(is_correct)

    if not confidences:
        return 0.0

    ece, _ = compute_ece(confidences, accuracies, n_bins=10)

    # Reward = 1 - scaled_ECE (perfect calibration → reward = 1)
    reward = 1.0 - config.ece_penalty_scale * ece
    return max(reward, -1.0)


def reward_helpfulness(
    predicted: list[Claim],
    ground_truth: list[dict],
    config: RewardConfig,
) -> float:
    """
    Helpfulness reward: penalize over-filtering and missed hallucinations.

    - Correctly supporting valid claims → bonus
    - Marking valid claims as contradicted → penalty (over-filtering)
    - Missing actual hallucinations → penalty
    """
    if not predicted:
        return 0.0

    gt_map = {}
    for gt in ground_truth:
        gt_map[gt.get("claim_text", "").lower().strip()] = gt.get("verdict", "supported")

    score = 0.0
    count = 0

    for claim in predicted:
        if claim.verdict is None:
            continue

        claim_text = claim.text.lower().strip()
        gt_verdict = gt_map.get(claim_text)
        if gt_verdict is None:
            gt_verdict = _find_closest_gt(claim_text, gt_map)
        if gt_verdict is None:
            continue

        count += 1

        if gt_verdict == "supported" and claim.verdict == ClaimVerdict.SUPPORTED:
            score += config.supported_bonus
        elif gt_verdict == "supported" and claim.verdict == ClaimVerdict.CONTRADICTED:
            score += config.over_filter_penalty  # over-filtering
        elif gt_verdict == "contradicted" and claim.verdict == ClaimVerdict.SUPPORTED:
            score += config.miss_penalty  # missed hallucination

    if count == 0:
        return 0.0
    return score / count


def reward_robustness(
    original_verdicts: list[ClaimVerdict],
    noisy_verdicts: list[ClaimVerdict],
    config: RewardConfig,
) -> float:
    """
    Robustness reward: verdicts should be stable under noise.

    Compare verdicts before and after noise injection.
    """
    if not original_verdicts or not noisy_verdicts:
        return 0.0

    n = min(len(original_verdicts), len(noisy_verdicts))
    score = 0.0

    for i in range(n):
        if original_verdicts[i] == noisy_verdicts[i]:
            score += config.noise_stability_bonus
        else:
            score += config.noise_flip_penalty

    return score / n


# ─────────────────────────────────────────────────────────────────
#  Combined Reward Function
# ─────────────────────────────────────────────────────────────────

class RewardFunction:
    """
    Combined multi-component reward function for PHIREN training.

    Returns a dict with individual components + total.
    """

    def __init__(self, config: Optional[RewardConfig] = None):
        self.config = config or RewardConfig()

    def compute(
        self,
        predicted: list[Claim],
        ground_truth: list[dict],
        original_verdicts: Optional[list[ClaimVerdict]] = None,
        noisy_verdicts: Optional[list[ClaimVerdict]] = None,
    ) -> dict[str, float]:
        """
        Compute the total reward and all components.

        Args:
            predicted: list of Claims with verdicts from the detector.
            ground_truth: list of {"claim_text": str, "verdict": str}.
            original_verdicts: verdicts without noise (for robustness).
            noisy_verdicts: verdicts with noise injection.

        Returns:
            Dict with keys: total, factuality, calibration,
            helpfulness, robustness.
        """
        # Individual rewards
        r_fact = reward_factuality(predicted, ground_truth, self.config)
        r_cal = reward_calibration(predicted, ground_truth, self.config)
        r_help = reward_helpfulness(predicted, ground_truth, self.config)

        r_robust = 0.0
        if original_verdicts and noisy_verdicts:
            r_robust = reward_robustness(
                original_verdicts, noisy_verdicts, self.config
            )

        # Weighted total
        total = (
            self.config.w_factuality * r_fact
            + self.config.w_calibration * r_cal
            + self.config.w_helpfulness * r_help
            + self.config.w_robustness * r_robust
        )

        # Clip
        total = max(self.config.min_reward, min(self.config.max_reward, total))

        return {
            "total": total,
            "factuality": r_fact,
            "calibration": r_cal,
            "helpfulness": r_help,
            "robustness": r_robust,
        }

    def update_weights(
        self,
        w_factuality: Optional[float] = None,
        w_calibration: Optional[float] = None,
        w_helpfulness: Optional[float] = None,
        w_robustness: Optional[float] = None,
    ) -> None:
        """Update reward weights (used by curriculum scheduler)."""
        if w_factuality is not None:
            self.config.w_factuality = w_factuality
        if w_calibration is not None:
            self.config.w_calibration = w_calibration
        if w_helpfulness is not None:
            self.config.w_helpfulness = w_helpfulness
        if w_robustness is not None:
            self.config.w_robustness = w_robustness

        total = (
            self.config.w_factuality + self.config.w_calibration
            + self.config.w_helpfulness + self.config.w_robustness
        )
        logger.info(
            f"Reward weights updated: fact={self.config.w_factuality:.2f} "
            f"cal={self.config.w_calibration:.2f} "
            f"help={self.config.w_helpfulness:.2f} "
            f"rob={self.config.w_robustness:.2f} (sum={total:.2f})"
        )
