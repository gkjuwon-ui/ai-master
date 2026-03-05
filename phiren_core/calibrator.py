"""
calibrator.py — PHIREN Confidence Calibrator

Post-hoc calibration module for PHIREN's hallucination detector.
Ensures that when the detector says "80% confident", the claim is
actually correct ~80% of the time.

Supports three calibration methods:
  - Temperature scaling (single learnable parameter)
  - Platt scaling (logistic regression on logits)
  - Isotonic regression (non-parametric)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from .protocol import CalibrationBucket, compute_ece

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Calibrator Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class CalibratorConfig:
    """Configuration for the PhirenCalibrator."""

    method: str = "temperature"          # temperature | platt | isotonic
    num_bins: int = 10                   # number of calibration bins
    temperature_init: float = 1.5        # initial temperature value
    learning_rate: float = 0.01          # LR for temperature optimization
    max_iter: int = 100                  # max optimization iterations
    patience: int = 10                   # early stopping patience

    # Multi-class (3-way NLI calibration)
    num_classes: int = 3                 # entailment, neutral, contradiction

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "num_bins": self.num_bins,
            "temperature_init": self.temperature_init,
            "num_classes": self.num_classes,
        }


# ─────────────────────────────────────────────────────────────────
#  Temperature Scaling
# ─────────────────────────────────────────────────────────────────

class TemperatureScaler(nn.Module):
    """
    Single learnable temperature parameter.
    Divides logits by T before softmax.
    Optimized via NLL on a held-out calibration set.
    """

    def __init__(self, init_temp: float = 1.5):
        super().__init__()
        self.temperature = nn.Parameter(
            torch.tensor(init_temp, dtype=torch.float32)
        )

    def forward(self, logits: torch.Tensor) -> torch.Tensor:
        """Scale logits by learned temperature."""
        return logits / self.temperature.clamp(min=0.01)

    def calibrate(self, logits: torch.Tensor) -> torch.Tensor:
        """Return calibrated probabilities."""
        scaled = self.forward(logits)
        return F.softmax(scaled, dim=-1)


# ─────────────────────────────────────────────────────────────────
#  Platt Scaling
# ─────────────────────────────────────────────────────────────────

class PlattScaler(nn.Module):
    """
    Platt scaling: logistic regression A*logit + B per class.
    More flexible than temperature scaling.
    """

    def __init__(self, num_classes: int = 3):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(num_classes))
        self.bias = nn.Parameter(torch.zeros(num_classes))

    def forward(self, logits: torch.Tensor) -> torch.Tensor:
        return logits * self.weight + self.bias

    def calibrate(self, logits: torch.Tensor) -> torch.Tensor:
        scaled = self.forward(logits)
        return F.softmax(scaled, dim=-1)


# ─────────────────────────────────────────────────────────────────
#  PHIREN Calibrator
# ─────────────────────────────────────────────────────────────────

class PhirenCalibrator(nn.Module):
    """
    Post-hoc calibrator for PHIREN's NLI verdicts.

    Usage:
        calibrator = PhirenCalibrator(config)
        calibrator.fit(val_logits, val_labels)     # learn calibration
        probs = calibrator.calibrate(test_logits)  # apply
        ece = calibrator.compute_ece(probs, labels)
    """

    def __init__(self, config: Optional[CalibratorConfig] = None):
        super().__init__()
        self.config = config or CalibratorConfig()

        # Initialize the appropriate scaler
        if self.config.method == "temperature":
            self.scaler = TemperatureScaler(self.config.temperature_init)
        elif self.config.method == "platt":
            self.scaler = PlattScaler(self.config.num_classes)
        else:
            self.scaler = None  # isotonic uses sklearn

        self._fitted = False
        self._isotonic_models = None  # for isotonic regression

        # Calibration history
        self._history: list[dict] = []

    def fit(
        self,
        logits: torch.Tensor,
        labels: torch.Tensor,
    ) -> dict[str, float]:
        """
        Fit the calibrator on a validation set.

        Args:
            logits: [N, C] — raw logits from the NLI head
            labels: [N]    — ground truth class indices

        Returns:
            Dict with fit metrics (pre_ece, post_ece, temperature, etc.)
        """
        logits = logits.detach().float()
        labels = labels.detach().long()

        # Pre-calibration ECE
        pre_probs = F.softmax(logits, dim=-1)
        pre_confidences = pre_probs.max(dim=-1).values
        pre_correct = (pre_probs.argmax(dim=-1) == labels).float()
        pre_ece, _ = compute_ece(
            pre_confidences.tolist(),
            pre_correct.tolist(),
            self.config.num_bins,
        )

        if self.config.method in ("temperature", "platt"):
            result = self._fit_parametric(logits, labels, pre_ece)
        elif self.config.method == "isotonic":
            result = self._fit_isotonic(logits, labels, pre_ece)
        else:
            raise ValueError(f"Unknown method: {self.config.method}")

        self._fitted = True
        self._history.append(result)
        return result

    def _fit_parametric(
        self,
        logits: torch.Tensor,
        labels: torch.Tensor,
        pre_ece: float,
    ) -> dict[str, float]:
        """Fit temperature or Platt scaling via gradient descent."""
        optimizer = torch.optim.LBFGS(
            self.scaler.parameters(),
            lr=self.config.learning_rate,
            max_iter=self.config.max_iter,
        )

        nll_criterion = nn.CrossEntropyLoss()

        def closure():
            optimizer.zero_grad()
            scaled = self.scaler(logits)
            loss = nll_criterion(scaled, labels)
            loss.backward()
            return loss

        optimizer.step(closure)

        # Post-calibration ECE
        with torch.no_grad():
            post_probs = self.scaler.calibrate(logits)
            post_confidences = post_probs.max(dim=-1).values
            post_correct = (post_probs.argmax(dim=-1) == labels).float()
            post_ece, buckets = compute_ece(
                post_confidences.tolist(),
                post_correct.tolist(),
                self.config.num_bins,
            )

        result = {
            "method": self.config.method,
            "pre_ece": pre_ece,
            "post_ece": post_ece,
            "ece_reduction": pre_ece - post_ece,
        }

        if self.config.method == "temperature":
            result["temperature"] = self.scaler.temperature.item()

        logger.info(
            f"Calibration fitted ({self.config.method}) | "
            f"ECE: {pre_ece:.4f} → {post_ece:.4f} "
            f"(Δ={pre_ece - post_ece:.4f})"
        )

        return result

    def _fit_isotonic(
        self,
        logits: torch.Tensor,
        labels: torch.Tensor,
        pre_ece: float,
    ) -> dict[str, float]:
        """Fit isotonic regression (non-parametric)."""
        try:
            from sklearn.isotonic import IsotonicRegression
        except ImportError:
            raise ImportError("pip install scikit-learn for isotonic calibration")

        probs = F.softmax(logits, dim=-1).numpy()
        labels_np = labels.numpy()

        self._isotonic_models = []
        for c in range(self.config.num_classes):
            ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            binary_labels = (labels_np == c).astype(float)
            ir.fit(probs[:, c], binary_labels)
            self._isotonic_models.append(ir)

        # Post-calibration ECE
        calibrated = self._apply_isotonic(probs)
        post_confidences = calibrated.max(axis=-1)
        post_correct = (calibrated.argmax(axis=-1) == labels_np).astype(float)
        post_ece, _ = compute_ece(
            post_confidences.tolist(),
            post_correct.tolist(),
            self.config.num_bins,
        )

        logger.info(
            f"Isotonic calibration fitted | ECE: {pre_ece:.4f} → {post_ece:.4f}"
        )

        return {
            "method": "isotonic",
            "pre_ece": pre_ece,
            "post_ece": post_ece,
            "ece_reduction": pre_ece - post_ece,
        }

    def _apply_isotonic(self, probs: np.ndarray) -> np.ndarray:
        """Apply fitted isotonic models to probabilities."""
        calibrated = np.zeros_like(probs)
        for c, ir in enumerate(self._isotonic_models):
            calibrated[:, c] = ir.predict(probs[:, c])
        # Re-normalize
        row_sums = calibrated.sum(axis=-1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-8)
        return calibrated / row_sums

    @torch.no_grad()
    def calibrate(self, logits: torch.Tensor) -> torch.Tensor:
        """
        Apply calibration to raw logits.

        Returns calibrated probabilities [N, C].
        """
        if not self._fitted:
            logger.warning("Calibrator not fitted, returning raw softmax")
            return F.softmax(logits, dim=-1)

        if self.config.method in ("temperature", "platt"):
            return self.scaler.calibrate(logits.float())
        elif self.config.method == "isotonic":
            probs = F.softmax(logits.float(), dim=-1).cpu().numpy()
            calibrated = self._apply_isotonic(probs)
            return torch.from_numpy(calibrated).to(logits.device)
        else:
            return F.softmax(logits, dim=-1)

    def compute_metrics(
        self,
        logits: torch.Tensor,
        labels: torch.Tensor,
    ) -> dict:
        """
        Compute comprehensive calibration metrics.

        Returns:
            Dict with ECE, MCE (max calibration error), Brier score,
            accuracy, and per-bin breakdown.
        """
        probs = self.calibrate(logits)
        confidences = probs.max(dim=-1).values
        predictions = probs.argmax(dim=-1)
        correct = (predictions == labels).float()

        # ECE
        ece, buckets = compute_ece(
            confidences.tolist(),
            correct.tolist(),
            self.config.num_bins,
        )

        # MCE (max calibration error)
        mce = max((b.calibration_error for b in buckets if b.count > 0), default=0.0)

        # Brier score
        one_hot = F.one_hot(labels, self.config.num_classes).float()
        brier = ((probs - one_hot) ** 2).sum(dim=-1).mean().item()

        # Accuracy
        accuracy = correct.mean().item()

        return {
            "ece": ece,
            "mce": mce,
            "brier_score": brier,
            "accuracy": accuracy,
            "calibration_buckets": [
                {
                    "bin_lower": b.bin_lower,
                    "bin_upper": b.bin_upper,
                    "avg_confidence": b.avg_confidence,
                    "avg_accuracy": b.avg_accuracy,
                    "count": b.count,
                    "error": b.calibration_error,
                }
                for b in buckets
            ],
        }

    # ──────────── Save / Load ────────────

    def save(self, path: str) -> None:
        """Save calibrator state."""
        import json
        from pathlib import Path

        save_dir = Path(path)
        save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / "calibrator_config.json", "w") as f:
            json.dump(self.config.to_dict(), f, indent=2)

        if self.scaler is not None:
            torch.save(self.scaler.state_dict(), save_dir / "scaler.pt")

        if self._isotonic_models is not None:
            import pickle
            with open(save_dir / "isotonic_models.pkl", "wb") as f:
                pickle.dump(self._isotonic_models, f)

        state = {"fitted": self._fitted, "history": self._history}
        with open(save_dir / "calibrator_state.json", "w") as f:
            json.dump(state, f, indent=2)

        logger.info(f"Calibrator saved to {save_dir}")

    @classmethod
    def load(cls, path: str) -> PhirenCalibrator:
        """Load a saved calibrator."""
        import json
        from pathlib import Path

        load_dir = Path(path)

        with open(load_dir / "calibrator_config.json") as f:
            cfg_dict = json.load(f)
        config = CalibratorConfig(**{
            k: v for k, v in cfg_dict.items()
            if k in CalibratorConfig.__dataclass_fields__
        })

        calibrator = cls(config)

        scaler_path = load_dir / "scaler.pt"
        if scaler_path.exists() and calibrator.scaler is not None:
            state = torch.load(scaler_path, map_location="cpu", weights_only=True)
            calibrator.scaler.load_state_dict(state)

        isotonic_path = load_dir / "isotonic_models.pkl"
        if isotonic_path.exists():
            import pickle
            with open(isotonic_path, "rb") as f:
                calibrator._isotonic_models = pickle.load(f)

        state_path = load_dir / "calibrator_state.json"
        if state_path.exists():
            with open(state_path) as f:
                state = json.load(f)
            calibrator._fitted = state.get("fitted", False)
            calibrator._history = state.get("history", [])

        logger.info(f"Calibrator loaded from {load_dir} (fitted={calibrator._fitted})")
        return calibrator
