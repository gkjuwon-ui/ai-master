"""
metrics.py — Evaluation Metrics for Ogenti Protocol

Provides standardized metrics for measuring protocol quality:
  - Compression Ratio (CR)
  - Semantic Fidelity (SF)
  - Cross-Agent Compatibility (CAC)
  - Protocol Stability Index (PSI)
  - Throughput (messages/sec)
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricResult:
    """A single metric measurement."""

    name: str
    value: float
    unit: str = ""
    details: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        u = f" {self.unit}" if self.unit else ""
        return f"{self.name}: {self.value:.4f}{u}"


@dataclass
class BenchmarkReport:
    """Full benchmark report across all metrics."""

    metrics: list[MetricResult] = field(default_factory=list)
    timestamp: str = ""
    config_summary: str = ""
    total_episodes: int = 0
    total_time_s: float = 0.0

    def add(self, metric: MetricResult) -> None:
        self.metrics.append(metric)

    def get(self, name: str) -> Optional[MetricResult]:
        for m in self.metrics:
            if m.name == name:
                return m
        return None

    def summary(self) -> dict:
        return {m.name: m.value for m in self.metrics}

    def pretty(self) -> str:
        lines = [
            "═══ Ogenti Benchmark Report ═══",
            f"Episodes: {self.total_episodes}",
            f"Time: {self.total_time_s:.1f}s",
            "───────────────────────────────",
        ]
        for m in self.metrics:
            u = f" {m.unit}" if m.unit else ""
            lines.append(f"  {m.name:.<30} {m.value:.4f}{u}")
        lines.append("═══════════════════════════════")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
#  Individual Metric Functions
# ─────────────────────────────────────────────────────────────────

def compression_ratio(
    original_tokens: list[int],
    protocol_tokens: list[int],
) -> MetricResult:
    """
    Compute average compression ratio.

    CR = mean(original_count / protocol_count) for each message pair.
    """
    if not original_tokens or not protocol_tokens:
        return MetricResult("compression_ratio", 0.0, "x")

    ratios = []
    for orig, proto in zip(original_tokens, protocol_tokens):
        if proto > 0:
            ratios.append(orig / proto)
    avg = sum(ratios) / len(ratios) if ratios else 0.0

    return MetricResult(
        "compression_ratio",
        avg,
        "x",
        {"min": min(ratios) if ratios else 0, "max": max(ratios) if ratios else 0},
    )


def semantic_fidelity(
    decoded_texts: list[str],
    references: list[str],
    method: str = "token_overlap",
) -> MetricResult:
    """
    Compute average semantic fidelity (accuracy of reconstruction).

    SF = mean(similarity(decoded, reference)) for each pair.
    """
    from ogenti_train.rewards import compute_semantic_similarity

    scores = []
    for dec, ref in zip(decoded_texts, references):
        scores.append(compute_semantic_similarity(dec, ref, method))

    avg = sum(scores) / len(scores) if scores else 0.0

    return MetricResult(
        "semantic_fidelity",
        avg,
        "",
        {
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "std": _std(scores),
            "method": method,
        },
    )


def cross_agent_compatibility(
    results_ab: list[float],
    results_cd: list[float],
) -> MetricResult:
    """
    Cross-Agent Compatibility: How well does the protocol work
    when agents are paired with partners they didn't train with?

    CAC = mean(accuracy_cross) / mean(accuracy_native)
    A value of 1.0 means the protocol is fully interoperable.
    """
    avg_native = sum(results_ab) / len(results_ab) if results_ab else 0.0
    avg_cross = sum(results_cd) / len(results_cd) if results_cd else 0.0

    cac = avg_cross / avg_native if avg_native > 0 else 0.0

    return MetricResult(
        "cross_agent_compatibility",
        min(1.0, cac),
        "",
        {"native_acc": avg_native, "cross_acc": avg_cross},
    )


def protocol_stability(
    accuracies: list[float],
    window: int = 100,
) -> MetricResult:
    """
    Protocol Stability Index: How consistent is the protocol
    over recent episodes?

    PSI = 1 - std(accuracies[-window:])
    High PSI = stable protocol, low variance.
    """
    recent = accuracies[-window:] if len(accuracies) > window else accuracies
    std = _std(recent)
    psi = max(0.0, 1.0 - 2.0 * std)

    return MetricResult(
        "protocol_stability",
        psi,
        "",
        {"std": std, "window": len(recent)},
    )


def throughput(
    num_messages: int,
    elapsed_seconds: float,
) -> MetricResult:
    """Messages processed per second."""
    tps = num_messages / elapsed_seconds if elapsed_seconds > 0 else 0.0
    return MetricResult(
        "throughput",
        tps,
        "msg/s",
        {"messages": num_messages, "seconds": elapsed_seconds},
    )


def token_budget_utilization(
    protocol_tokens: list[int],
    budgets: list[int],
) -> MetricResult:
    """
    How efficiently agents use the available token budget.

    Utilization = mean(used / budget).
    Ideal: high compression but using most of the budget
    (not wasting capacity).
    """
    utils = []
    for used, budget in zip(protocol_tokens, budgets):
        if budget > 0:
            utils.append(used / budget)
    avg = sum(utils) / len(utils) if utils else 0.0

    return MetricResult(
        "budget_utilization",
        avg,
        "",
        {
            "min": min(utils) if utils else 0,
            "max": max(utils) if utils else 0,
        },
    )


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

def _std(values: list[float]) -> float:
    """Standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)
