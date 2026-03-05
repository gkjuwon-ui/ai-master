"""
PHIREN Core — Hallucination Detection & Factuality Verification Engine

PHIREN trains models to detect hallucinations in LLM outputs by
decomposing text into atomic claims, verifying each claim against
source context, and producing calibrated confidence scores.

Architecture:
  Text + Context → ClaimExtractor → [Claim₁, Claim₂, ...] → Verifier
  Verifier → per-claim verdict (supported / contradicted / unverifiable)
  Calibrator → factuality_score + calibration_score

MARL: Extractor + Verifier co-evolve via reward signals
      (factuality, calibration, helpfulness, robustness)
"""

from .protocol import (
    ClaimConfig,
    Claim,
    ClaimVerdict,
    VerificationMessage,
    VerificationMode,
    CalibrationBucket,
)
from .detector import PhirenDetector, DetectorConfig
from .calibrator import PhirenCalibrator, CalibratorConfig
from .channel import VerificationChannel

__all__ = [
    "ClaimConfig",
    "Claim",
    "ClaimVerdict",
    "VerificationMessage",
    "VerificationMode",
    "CalibrationBucket",
    "PhirenDetector",
    "DetectorConfig",
    "PhirenCalibrator",
    "CalibratorConfig",
    "VerificationChannel",
]

__version__ = "0.1.0"
