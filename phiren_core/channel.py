"""
channel.py — PHIREN Verification Channel

Routes claims through the verification pipeline.
Analogous to ogenti_core.channel (CommunicationChannel) but
designed for hallucination detection rather than compression.

Pipeline stages:
  1. TEXT → Claim Extraction (Detector)
  2. Claims → NLI Verification (Detector)
  3. Verified claims → Calibration (Calibrator)
  4. Calibrated results → VerificationMessage
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Optional

from .protocol import (
    Claim,
    ClaimConfig,
    ClaimVerdict,
    VerificationMessage,
    VerificationMode,
    compute_ece,
    compute_factuality_score,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Channel Statistics
# ─────────────────────────────────────────────────────────────────

@dataclass
class ChannelStats:
    """Running statistics for the verification channel."""

    total_texts: int = 0
    total_claims: int = 0
    total_supported: int = 0
    total_contradicted: int = 0
    total_unverifiable: int = 0
    avg_factuality: float = 0.0
    avg_calibration: float = 0.0
    avg_claims_per_text: float = 0.0
    avg_latency_ms: float = 0.0

    # Per-category stats
    category_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    category_accuracy: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    # History
    _factuality_history: list[float] = field(default_factory=list)
    _latency_history: list[float] = field(default_factory=list)

    def update(self, msg: VerificationMessage, latency_ms: float) -> None:
        """Update stats with a new verification result."""
        self.total_texts += 1
        self.total_claims += msg.total_claims
        self.total_supported += msg.supported_claims
        self.total_contradicted += msg.contradicted_claims
        self.total_unverifiable += msg.unverifiable_claims

        self._factuality_history.append(msg.factuality_score)
        self._latency_history.append(latency_ms)

        # Rolling averages
        n = len(self._factuality_history)
        self.avg_factuality = sum(self._factuality_history) / n
        self.avg_latency_ms = sum(self._latency_history) / n

        if self.total_texts > 0:
            self.avg_claims_per_text = self.total_claims / self.total_texts

        # Per-category
        for claim in msg.claims:
            cat = claim.category.value
            self.category_counts[cat] = self.category_counts.get(cat, 0) + 1

    def to_dict(self) -> dict:
        return {
            "total_texts": self.total_texts,
            "total_claims": self.total_claims,
            "total_supported": self.total_supported,
            "total_contradicted": self.total_contradicted,
            "total_unverifiable": self.total_unverifiable,
            "avg_factuality": round(self.avg_factuality, 4),
            "avg_calibration": round(self.avg_calibration, 4),
            "avg_claims_per_text": round(self.avg_claims_per_text, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "category_counts": dict(self.category_counts),
        }

    def summary(self) -> str:
        return (
            f"ChannelStats(texts={self.total_texts}, "
            f"claims={self.total_claims}, "
            f"factuality={self.avg_factuality:.3f}, "
            f"latency={self.avg_latency_ms:.0f}ms)"
        )


# ─────────────────────────────────────────────────────────────────
#  Hook Type
# ─────────────────────────────────────────────────────────────────

VerificationHook = Callable[[VerificationMessage], Optional[VerificationMessage]]


# ─────────────────────────────────────────────────────────────────
#  Verification Channel
# ─────────────────────────────────────────────────────────────────

class VerificationChannel:
    """
    Thread-safe pipeline that routes text through claim extraction,
    NLI verification, and calibration.

    Supports hooks at each stage for monitoring, logging, or
    modifying behavior during training.

    Usage:
        channel = VerificationChannel(config)
        channel.register_detector(detector)
        channel.register_calibrator(calibrator)

        result = channel.verify("Paris is the capital of Germany.",
                                context="Paris is the capital of France.")
        print(result.factuality_score)  # low — contradiction
    """

    def __init__(self, config: Optional[ClaimConfig] = None):
        self.config = config or ClaimConfig()
        self.stats = ChannelStats()
        self._lock = Lock()

        # Registered components
        self._detector = None
        self._calibrator = None

        # Hooks
        self._pre_hooks: list[VerificationHook] = []
        self._post_hooks: list[VerificationHook] = []
        self._claim_hooks: list[Callable[[list[Claim]], list[Claim]]] = []

        # Noise injection (for robustness training)
        self._noise_enabled = config.enable_noise if config else False
        self._noise_rate = config.noise_rate if config else 0.0

        # Message log
        self._message_log: list[dict] = []
        self._max_log_size = 1000

    # ──────────── Registration ────────────

    def register_detector(self, detector) -> None:
        """Register a PhirenDetector instance."""
        self._detector = detector
        logger.info("Detector registered with verification channel")

    def register_calibrator(self, calibrator) -> None:
        """Register a PhirenCalibrator instance."""
        self._calibrator = calibrator
        logger.info("Calibrator registered with verification channel")

    def add_pre_hook(self, hook: VerificationHook) -> None:
        """Add a pre-verification hook."""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: VerificationHook) -> None:
        """Add a post-verification hook."""
        self._post_hooks.append(hook)

    def add_claim_hook(self, hook: Callable[[list[Claim]], list[Claim]]) -> None:
        """Add a claim-processing hook (between extraction and verification)."""
        self._claim_hooks.append(hook)

    # ──────────── Core Pipeline ────────────

    def verify(
        self,
        text: str,
        context: str,
        mode: Optional[VerificationMode] = None,
    ) -> VerificationMessage:
        """
        Run the full verification pipeline.

        1. Run pre-hooks
        2. Extract claims (via detector)
        3. Run claim hooks (e.g., filtering)
        4. Verify claims (via detector NLI)
        5. Calibrate confidences (if calibrator registered)
        6. Compute aggregate scores
        7. Run post-hooks
        8. Update stats
        """
        start_time = time.time()
        mode = mode or self.config.verification_mode

        # Build initial message
        msg = VerificationMessage(text=text, context=context, mode=mode)

        # Pre-hooks
        for hook in self._pre_hooks:
            result = hook(msg)
            if result is not None:
                msg = result

        # Stage 1: Claim extraction
        if self._detector is not None:
            claims = self._detector.extract_claims(msg.text)
        else:
            claims = self._fallback_extract(msg.text)

        # Claim hooks
        for hook in self._claim_hooks:
            claims = hook(claims)

        # Stage 2: NLI verification
        if self._detector is not None:
            claims = self._detector.verify_claims(claims, msg.context)
        else:
            for claim in claims:
                claim.verdict = ClaimVerdict.UNVERIFIABLE
                claim.confidence = 0.5

        # Noise injection (for training robustness)
        if self._noise_enabled and self._noise_rate > 0:
            claims = self._inject_noise(claims)

        # Stage 3: Calibration
        if self._calibrator is not None and self._calibrator._fitted:
            claims = self._calibrate_claims(claims)

        # Compute aggregates
        msg.claims = claims
        msg.factuality_score = compute_factuality_score(claims)

        # Compute calibration
        if claims:
            confidences = [c.confidence for c in claims]
            accuracies = [
                1.0 if c.verdict == ClaimVerdict.SUPPORTED else 0.0
                for c in claims
            ]
            ece, buckets = compute_ece(
                confidences, accuracies, self.config.num_calibration_bins
            )
            msg.calibration_score = 1.0 - ece
            msg.calibration_buckets = buckets

        # Post-hooks
        for hook in self._post_hooks:
            result = hook(msg)
            if result is not None:
                msg = result

        # Stats
        latency_ms = (time.time() - start_time) * 1000
        with self._lock:
            self.stats.update(msg, latency_ms)
            self._log_message(msg, latency_ms)

        return msg

    def verify_batch(
        self,
        texts: list[str],
        contexts: list[str],
        mode: Optional[VerificationMode] = None,
    ) -> list[VerificationMessage]:
        """Verify a batch of texts. Sequential for now."""
        results = []
        for text, context in zip(texts, contexts):
            result = self.verify(text, context, mode)
            results.append(result)
        return results

    # ──────────── Noise Injection ────────────

    def set_noise(self, enabled: bool, rate: float = 0.0) -> None:
        """Enable/disable noise injection for robustness training."""
        self._noise_enabled = enabled
        self._noise_rate = rate
        logger.info(f"Noise injection: enabled={enabled}, rate={rate:.2f}")

    def _inject_noise(self, claims: list[Claim]) -> list[Claim]:
        """Randomly flip claim verdicts for robustness training."""
        import random
        verdicts = [ClaimVerdict.SUPPORTED, ClaimVerdict.CONTRADICTED, ClaimVerdict.UNVERIFIABLE]
        for claim in claims:
            if random.random() < self._noise_rate:
                original = claim.verdict
                claim.verdict = random.choice(
                    [v for v in verdicts if v != original]
                )
        return claims

    # ──────────── Calibration ────────────

    def _calibrate_claims(self, claims: list[Claim]) -> list[Claim]:
        """Apply calibrator to adjust confidence scores."""
        import torch

        if not claims:
            return claims

        # Build pseudo-logits from NLI scores
        logits = []
        for claim in claims:
            scores = claim.nli_scores
            if scores:
                logit = [
                    scores.get("contradiction", 0.0),
                    scores.get("neutral", 0.0),
                    scores.get("entailment", 0.0),
                ]
            else:
                logit = [0.33, 0.33, 0.34]
            logits.append(logit)

        logits_tensor = torch.tensor(logits, dtype=torch.float32)
        calibrated_probs = self._calibrator.calibrate(logits_tensor)

        for i, claim in enumerate(claims):
            probs = calibrated_probs[i]
            claim.confidence = probs.max().item()
            # Update NLI scores with calibrated values
            claim.nli_scores = {
                "contradiction": probs[0].item(),
                "neutral": probs[1].item(),
                "entailment": probs[2].item(),
            }

        return claims

    # ──────────── Fallback ────────────

    @staticmethod
    def _fallback_extract(text: str) -> list[Claim]:
        """Simple sentence splitting when no detector is registered."""
        import re
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [
            Claim(claim_id=i, text=s.strip())
            for i, s in enumerate(sentences)
            if len(s.strip()) >= 5
        ]

    # ──────────── Logging ────────────

    def _log_message(self, msg: VerificationMessage, latency_ms: float) -> None:
        """Log message to history."""
        entry = {
            "timestamp": time.time(),
            "total_claims": msg.total_claims,
            "factuality": msg.factuality_score,
            "calibration": msg.calibration_score,
            "latency_ms": latency_ms,
            "mode": msg.mode.value,
        }
        self._message_log.append(entry)
        if len(self._message_log) > self._max_log_size:
            self._message_log = self._message_log[-self._max_log_size:]

    def get_log(self, last_n: int = 50) -> list[dict]:
        """Get recent verification log entries."""
        return self._message_log[-last_n:]

    # ──────────── State ────────────

    def get_stats(self) -> dict:
        """Get current channel statistics."""
        with self._lock:
            return self.stats.to_dict()

    def reset_stats(self) -> None:
        """Reset statistics."""
        with self._lock:
            self.stats = ChannelStats()
            self._message_log.clear()
            logger.info("Channel stats reset")

    def __repr__(self) -> str:
        return (
            f"VerificationChannel("
            f"detector={'✓' if self._detector else '✗'}, "
            f"calibrator={'✓' if self._calibrator else '✗'}, "
            f"noise={self._noise_enabled}, "
            f"texts={self.stats.total_texts})"
        )
