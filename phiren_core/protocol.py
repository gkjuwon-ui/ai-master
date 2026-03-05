"""
protocol.py — PHIREN Verification Protocol Definition

Defines the structure of verification messages that agents exchange
during hallucination detection training and inference.

Key Design Choice: Unlike OGENTI (token compression) and OVISEN
(embedding compression), PHIREN focuses on *factuality verification*.
The protocol message structure carries per-claim verdicts, confidence
scores, and evidence pointers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Optional


# ─────────────────────────────────────────────────────────────────
#  Verification Mode
# ─────────────────────────────────────────────────────────────────

class VerificationMode(str, Enum):
    """How aggressively to verify claims."""
    FULL = "full"          # decompose + verify every claim
    QUICK = "quick"        # skip decomposition, score holistically
    STRICT = "strict"      # treat unverifiable as contradicted


# ─────────────────────────────────────────────────────────────────
#  Claim Verdict
# ─────────────────────────────────────────────────────────────────

class ClaimVerdict(str, Enum):
    """Per-claim verification result."""
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"


# ─────────────────────────────────────────────────────────────────
#  Claim Categories
# ─────────────────────────────────────────────────────────────────

class ClaimCategory(str, Enum):
    """Semantic category of an extracted claim."""
    FACTUAL = "factual"              # verifiable against external knowledge
    NUMERICAL = "numerical"          # contains specific numbers / quantities
    TEMPORAL = "temporal"            # time-bound assertions
    CAUSAL = "causal"                # A causes B
    COMPARATIVE = "comparative"      # A > B, A is better than B
    DEFINITIONAL = "definitional"    # X is defined as Y
    EXISTENTIAL = "existential"      # X exists / was created by Y
    SUBJECTIVE = "subjective"        # opinion — cannot be verified
    META = "meta"                    # about the model itself ("I think...")


# ─────────────────────────────────────────────────────────────────
#  Claim Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class ClaimConfig:
    """Configuration for the claim extraction & verification protocol."""

    # Claim extraction
    max_claims_per_text: int = 20
    min_claim_length: int = 5          # characters
    max_claim_length: int = 200        # characters

    # Verification
    verification_mode: VerificationMode = VerificationMode.FULL
    confidence_threshold: float = 0.5  # below → UNVERIFIABLE
    contradiction_threshold: float = 0.3  # below → CONTRADICTED

    # NLI model
    nli_model_name: str = "cross-encoder/nli-deberta-v3-base"

    # Calibration
    num_calibration_bins: int = 10
    calibration_method: str = "temperature"  # temperature | platt | isotonic

    # Budget
    max_context_tokens: int = 512
    max_text_tokens: int = 1024

    # Error injection (for robustness training)
    enable_noise: bool = False
    noise_rate: float = 0.0   # fraction of claims to randomly flip

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verification_mode"] = self.verification_mode.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ClaimConfig:
        if "verification_mode" in d and isinstance(d["verification_mode"], str):
            d["verification_mode"] = VerificationMode(d["verification_mode"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─────────────────────────────────────────────────────────────────
#  Claim
# ─────────────────────────────────────────────────────────────────

@dataclass
class Claim:
    """
    An atomic factual claim extracted from text.

    Example:
      Text: "Paris, founded in 3rd century BC, is the capital of France."
      Claims:
        - Claim("Paris was founded in the 3rd century BC", TEMPORAL)
        - Claim("Paris is the capital of France", FACTUAL)
    """
    claim_id: int
    text: str
    category: ClaimCategory = ClaimCategory.FACTUAL

    # Verification result (filled after verification)
    verdict: Optional[ClaimVerdict] = None
    confidence: float = 0.0           # model's confidence in its verdict
    evidence_span: str = ""           # relevant span from context
    nli_scores: dict = field(default_factory=dict)  # entail/neutral/contradict

    # Position in source text
    source_start: int = 0
    source_end: int = 0

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "category": self.category.value,
            "verdict": self.verdict.value if self.verdict else None,
            "confidence": self.confidence,
            "evidence_span": self.evidence_span,
            "nli_scores": self.nli_scores,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Claim:
        return cls(
            claim_id=d["claim_id"],
            text=d["text"],
            category=ClaimCategory(d.get("category", "factual")),
            verdict=ClaimVerdict(d["verdict"]) if d.get("verdict") else None,
            confidence=d.get("confidence", 0.0),
            evidence_span=d.get("evidence_span", ""),
            nli_scores=d.get("nli_scores", {}),
        )


# ─────────────────────────────────────────────────────────────────
#  Calibration Bucket
# ─────────────────────────────────────────────────────────────────

@dataclass
class CalibrationBucket:
    """A single bin in the calibration histogram."""
    bin_lower: float
    bin_upper: float
    avg_confidence: float = 0.0
    avg_accuracy: float = 0.0
    count: int = 0

    @property
    def calibration_error(self) -> float:
        """Absolute difference: |confidence - accuracy|."""
        return abs(self.avg_confidence - self.avg_accuracy)


# ─────────────────────────────────────────────────────────────────
#  Verification Message
# ─────────────────────────────────────────────────────────────────

@dataclass
class VerificationMessage:
    """
    A complete verification result for a piece of text.

    Contains all extracted claims, their verdicts, and aggregate
    factuality & calibration scores.
    """

    text: str
    context: str
    claims: list[Claim] = field(default_factory=list)
    mode: VerificationMode = VerificationMode.FULL

    # Aggregate scores
    factuality_score: float = 0.0     # fraction of supported claims
    calibration_score: float = 0.0    # 1 - ECE (expected calibration error)
    calibration_buckets: list[CalibrationBucket] = field(default_factory=list)

    # Metadata
    metadata: dict = field(default_factory=dict)

    @property
    def total_claims(self) -> int:
        return len(self.claims)

    @property
    def supported_claims(self) -> int:
        return sum(1 for c in self.claims if c.verdict == ClaimVerdict.SUPPORTED)

    @property
    def contradicted_claims(self) -> int:
        return sum(1 for c in self.claims if c.verdict == ClaimVerdict.CONTRADICTED)

    @property
    def unverifiable_claims(self) -> int:
        return sum(1 for c in self.claims if c.verdict == ClaimVerdict.UNVERIFIABLE)

    @property
    def fingerprint(self) -> str:
        """Deterministic hash for caching."""
        raw = json.dumps({
            "text": self.text[:200],
            "context": self.context[:200],
            "claims": len(self.claims),
        }, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "context": self.context,
            "claims": [c.to_dict() for c in self.claims],
            "mode": self.mode.value,
            "factuality_score": self.factuality_score,
            "calibration_score": self.calibration_score,
            "total_claims": self.total_claims,
            "supported": self.supported_claims,
            "contradicted": self.contradicted_claims,
            "unverifiable": self.unverifiable_claims,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> VerificationMessage:
        return cls(
            text=d["text"],
            context=d["context"],
            claims=[Claim.from_dict(c) for c in d.get("claims", [])],
            mode=VerificationMode(d.get("mode", "full")),
            factuality_score=d.get("factuality_score", 0.0),
            calibration_score=d.get("calibration_score", 0.0),
        )

    def __repr__(self) -> str:
        return (
            f"VerificationMessage("
            f"claims={self.total_claims}, "
            f"supported={self.supported_claims}, "
            f"contradicted={self.contradicted_claims}, "
            f"factuality={self.factuality_score:.2f})"
        )


# ─────────────────────────────────────────────────────────────────
#  Utility Functions
# ─────────────────────────────────────────────────────────────────

def compute_factuality_score(claims: list[Claim]) -> float:
    """
    Compute factuality score from claim verdicts.

    Score = supported / (supported + contradicted)
    Unverifiable claims are excluded from the denominator.
    """
    supported = sum(1 for c in claims if c.verdict == ClaimVerdict.SUPPORTED)
    contradicted = sum(1 for c in claims if c.verdict == ClaimVerdict.CONTRADICTED)
    total = supported + contradicted
    if total == 0:
        return 1.0  # no verifiable claims → assume factual
    return supported / total


def compute_ece(
    confidences: list[float],
    accuracies: list[float],
    n_bins: int = 10,
) -> tuple[float, list[CalibrationBucket]]:
    """
    Compute Expected Calibration Error (ECE).

    Returns (ECE, list of calibration buckets).
    """
    if not confidences:
        return 0.0, []

    buckets = []
    for i in range(n_bins):
        lower = i / n_bins
        upper = (i + 1) / n_bins
        buckets.append(CalibrationBucket(bin_lower=lower, bin_upper=upper))

    for conf, acc in zip(confidences, accuracies):
        bin_idx = min(int(conf * n_bins), n_bins - 1)
        b = buckets[bin_idx]
        old_sum_conf = b.avg_confidence * b.count
        old_sum_acc = b.avg_accuracy * b.count
        b.count += 1
        b.avg_confidence = (old_sum_conf + conf) / b.count
        b.avg_accuracy = (old_sum_acc + acc) / b.count

    # ECE = weighted average of |confidence - accuracy| per bin
    total = sum(b.count for b in buckets)
    if total == 0:
        return 0.0, buckets

    ece = sum(
        (b.count / total) * b.calibration_error
        for b in buckets if b.count > 0
    )
    return ece, buckets
