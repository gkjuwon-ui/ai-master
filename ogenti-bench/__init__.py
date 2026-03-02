"""
ogenti-bench — Benchmark & Evaluation Suite for Ogenti Protocol

Modules:
  metrics    — Individual metric functions (CR, SF, CAC, PSI)
  benchmark  — Full benchmark runner
  visualize  — Training curve & protocol evolution plots
"""

__version__ = "0.1.0"

from ogenti_bench.metrics import (
    BenchmarkReport,
    MetricResult,
    compression_ratio,
    semantic_fidelity,
    cross_agent_compatibility,
    protocol_stability,
    throughput,
    token_budget_utilization,
)
from ogenti_bench.benchmark import OgentiBenchmark
from ogenti_bench.visualize import (
    plot_training_curves,
    plot_compression_vs_accuracy,
    plot_token_distribution,
    plot_phase_summary,
    generate_all_plots,
)

__all__ = [
    "BenchmarkReport",
    "MetricResult",
    "OgentiBenchmark",
    "compression_ratio",
    "semantic_fidelity",
    "cross_agent_compatibility",
    "protocol_stability",
    "throughput",
    "token_budget_utilization",
    "plot_training_curves",
    "plot_compression_vs_accuracy",
    "plot_token_distribution",
    "plot_phase_summary",
    "generate_all_plots",
]
