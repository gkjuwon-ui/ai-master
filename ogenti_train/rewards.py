"""
rewards.py — Reward Functions for MARL Training

Implements the multi-component reward function from OGENTI_SYSTEM_DESIGN.md:

  R = w_acc · R_accuracy
    + w_eff · R_efficiency
    + w_cla · R_clarity
    + w_gen · R_generalization

Weights (default):
  accuracy:       0.40
  efficiency:     0.30
  clarity:        0.20
  generalization: 0.10
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Reward Config
# ─────────────────────────────────────────────────────────────────

@dataclass
class RewardConfig:
    """Weights and thresholds for the reward function."""

    # Component weights (sum to 1.0)
    w_accuracy: float = 0.40
    w_efficiency: float = 0.30
    w_clarity: float = 0.20
    w_generalization: float = 0.10

    # Efficiency params
    target_compression: float = 15.0   # Target compression ratio
    efficiency_scale: float = 5.0      # Controls sharpness of efficiency curve

    # Clarity params
    consistency_window: int = 10       # Recent episodes to check consistency

    # Penalty
    budget_violation_penalty: float = -1.0  # Penalty for exceeding token budget
    empty_message_penalty: float = -0.5     # Penalty for producing empty output


# ─────────────────────────────────────────────────────────────────
#  Semantic Similarity (lightweight)
# ─────────────────────────────────────────────────────────────────

def compute_semantic_similarity(
    text_a: str,
    text_b: str,
    method: str = "token_overlap",
) -> float:
    """
    Compute semantic similarity between two texts.

    Methods
    -------
    - "token_overlap": Simple token-level Jaccard similarity (fast, no model needed)
    - "embedding": Cosine similarity of sentence embeddings (requires model)

    For early training, token_overlap is sufficient.
    Embedding-based comparison is used for benchmark evaluation.
    """
    if method == "token_overlap":
        return _token_overlap(text_a, text_b)
    elif method == "embedding":
        return _embedding_similarity(text_a, text_b)
    else:
        raise ValueError(f"Unknown similarity method: {method}")


def _token_overlap(text_a: str, text_b: str) -> float:
    """
    Token-level Jaccard similarity + order-aware bonus.

    Returns a value in [0, 1].
    """
    if not text_a or not text_b:
        return 0.0

    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    jaccard = len(intersection) / len(union)

    # Order-aware bonus: check subsequence of overlapping tokens
    list_a = text_a.lower().split()
    list_b = text_b.lower().split()

    # Longest common subsequence ratio
    lcs_len = _lcs_length(list_a, list_b)
    lcs_ratio = lcs_len / max(len(list_a), len(list_b))

    # Weighted combination: 60% Jaccard + 40% LCS
    return 0.6 * jaccard + 0.4 * lcs_ratio


def _lcs_length(a: list[str], b: list[str]) -> int:
    """Compute length of longest common subsequence."""
    m, n = len(a), len(b)
    # Space-optimized DP
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, [0] * (n + 1)
    return prev[n] if m > 0 else 0


def _embedding_similarity(text_a: str, text_b: str) -> float:
    """
    Cosine similarity using sentence-transformers.

    Lazy-loaded to avoid import overhead when not needed.
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        logger.warning(
            "sentence-transformers not installed, falling back to token_overlap"
        )
        return _token_overlap(text_a, text_b)

    # Use a lightweight model
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode([text_a, text_b], convert_to_numpy=True)

    cos_sim = float(
        np.dot(embeddings[0], embeddings[1])
        / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]) + 1e-8)
    )
    return max(0.0, cos_sim)  # Clamp to [0, 1]


# ─────────────────────────────────────────────────────────────────
#  Reward Components
# ─────────────────────────────────────────────────────────────────

def reward_accuracy(
    decoded_text: str,
    reference: str,
    method: str = "token_overlap",
) -> float:
    """
    R_accuracy: How well did the decoder reconstruct the intent?

    Range: [0, 1]
    """
    return compute_semantic_similarity(decoded_text, reference, method)


def reward_efficiency(
    protocol_tokens: int,
    original_tokens: int,
    target_compression: float = 15.0,
    scale: float = 5.0,
) -> float:
    """
    R_efficiency: How much compression was achieved?

    Uses a sigmoid-shaped curve centered at the target compression ratio.
    - Below target: partial reward
    - At target: 0.5
    - Above target: approaches 1.0

    Range: [0, 1]
    """
    if protocol_tokens == 0:
        return 0.0  # Empty message → no efficiency reward

    compression = original_tokens / protocol_tokens

    # Sigmoid: 1 / (1 + exp(-k * (x - target)))
    x = (compression - target_compression) / scale
    return 1.0 / (1.0 + math.exp(-x))


def reward_clarity(
    current_accuracy: float,
    recent_accuracies: list[float],
) -> float:
    """
    R_clarity: Consistency of the protocol.

    Agents are rewarded for maintaining stable accuracy across
    recent episodes (low variance = clear, learnable protocol).

    Range: [0, 1]
    """
    if len(recent_accuracies) < 2:
        return 0.5  # Not enough data yet

    # Include current
    accuracies = recent_accuracies + [current_accuracy]
    mean = sum(accuracies) / len(accuracies)
    variance = sum((a - mean) ** 2 for a in accuracies) / len(accuracies)
    std = math.sqrt(variance)

    # Low std → high clarity, std of 0.5 → clarity near 0
    clarity = max(0.0, 1.0 - 2.0 * std)
    return clarity


def reward_generalization(
    accuracy_seen: float,
    accuracy_unseen: float,
) -> float:
    """
    R_generalization: How well does the protocol work on unseen tasks?

    Ratio of unseen accuracy to seen accuracy.
    If the agent performs as well on unseen tasks as seen ones,
    generalization reward = 1.0.

    Range: [0, 1]
    """
    if accuracy_seen < 0.01:
        return 0.0  # Can't generalize if can't even do seen tasks
    ratio = accuracy_unseen / accuracy_seen
    return min(1.0, ratio)


# ─────────────────────────────────────────────────────────────────
#  Combined Reward Function
# ─────────────────────────────────────────────────────────────────

class RewardFunction:
    """
    Multi-component reward function for MARL training.

    Combines accuracy, efficiency, clarity, and generalization
    into a single scalar reward signal.
    """

    def __init__(self, config: Optional[RewardConfig] = None):
        self.config = config or RewardConfig()
        self._recent_accuracies: list[float] = []

    def compute(
        self,
        decoded_text: str,
        reference: str,
        protocol_tokens: int,
        original_tokens: int,
        budget: int,
        accuracy_unseen: float = 0.0,
        similarity_method: str = "token_overlap",
    ) -> dict[str, float]:
        """
        Compute the full reward.

        Parameters
        ----------
        decoded_text : str
            What the decoder produced.
        reference : str
            Ground truth.
        protocol_tokens : int
            Number of tokens in the protocol message.
        original_tokens : int
            Number of tokens in the original NL instruction.
        budget : int
            Current token budget (for violation check).
        accuracy_unseen : float
            Accuracy on held-out tasks (for generalization).
        similarity_method : str
            Which similarity method to use.

        Returns
        -------
        dict with keys: accuracy, efficiency, clarity, generalization,
                       total, penalties, breakdown
        """
        cfg = self.config

        # Penalties
        penalty = 0.0
        if protocol_tokens > budget:
            penalty += cfg.budget_violation_penalty
        if not decoded_text.strip():
            penalty += cfg.empty_message_penalty

        # Components
        r_acc = reward_accuracy(decoded_text, reference, similarity_method)
        r_eff = reward_efficiency(
            protocol_tokens, original_tokens,
            cfg.target_compression, cfg.efficiency_scale,
        )
        r_cla = reward_clarity(
            r_acc,
            self._recent_accuracies[-cfg.consistency_window:],
        )
        r_gen = reward_generalization(r_acc, accuracy_unseen)

        # Track for clarity
        self._recent_accuracies.append(r_acc)
        if len(self._recent_accuracies) > cfg.consistency_window * 2:
            self._recent_accuracies = self._recent_accuracies[-cfg.consistency_window:]

        # Weighted sum
        total = (
            cfg.w_accuracy * r_acc
            + cfg.w_efficiency * r_eff
            + cfg.w_clarity * r_cla
            + cfg.w_generalization * r_gen
            + penalty
        )

        return {
            "total": total,
            "accuracy": r_acc,
            "efficiency": r_eff,
            "clarity": r_cla,
            "generalization": r_gen,
            "penalty": penalty,
            "compression_ratio": (
                original_tokens / protocol_tokens
                if protocol_tokens > 0 else 0.0
            ),
            "protocol_tokens": protocol_tokens,
            "budget": budget,
        }

    def reset(self) -> None:
        """Reset tracked state (e.g. between phases)."""
        self._recent_accuracies.clear()
