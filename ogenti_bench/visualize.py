"""
visualize.py — Training Visualization Utilities

Generates plots for:
  - Training curves (reward, accuracy, compression over episodes)
  - Phase transitions
  - Protocol evolution (token distribution changes)
  - Compression vs accuracy tradeoff
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def plot_training_curves(
    metrics_log: list[dict],
    output_path: str = "training_curves.png",
    show: bool = False,
) -> None:
    """
    Plot reward, accuracy, and compression ratio over episodes.

    Parameters
    ----------
    metrics_log : list[dict]
        List of per-episode metric dicts (from trainer._metrics_log).
    output_path : str
        Where to save the figure.
    show : bool
        Whether to plt.show() interactively.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend
    except ImportError:
        logger.warning("matplotlib not installed, skipping visualization")
        return

    episodes = [m.get("episode", i) for i, m in enumerate(metrics_log)]
    rewards = [m.get("total_reward", 0) for m in metrics_log]
    accuracies = [m.get("accuracy", 0) for m in metrics_log]
    compressions = [m.get("compression_ratio", 0) for m in metrics_log]
    phases = [m.get("phase", 0) for m in metrics_log]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    # Smoothing helper
    def smooth(vals, window=50):
        if len(vals) < window:
            return vals
        smoothed = []
        for i in range(len(vals)):
            start = max(0, i - window + 1)
            smoothed.append(sum(vals[start:i+1]) / (i - start + 1))
        return smoothed

    # Reward
    axes[0].plot(episodes, smooth(rewards), color="#2196F3", linewidth=1.5)
    axes[0].fill_between(episodes, 0, smooth(rewards), alpha=0.1, color="#2196F3")
    axes[0].set_ylabel("Reward")
    axes[0].set_title("Ogenti Training Progress")
    axes[0].grid(True, alpha=0.3)

    # Accuracy
    axes[1].plot(episodes, smooth(accuracies), color="#4CAF50", linewidth=1.5)
    axes[1].fill_between(episodes, 0, smooth(accuracies), alpha=0.1, color="#4CAF50")
    axes[1].set_ylabel("Accuracy")
    axes[1].set_ylim(0, 1)
    axes[1].grid(True, alpha=0.3)

    # Compression
    axes[2].plot(episodes, smooth(compressions), color="#FF9800", linewidth=1.5)
    axes[2].fill_between(episodes, 0, smooth(compressions), alpha=0.1, color="#FF9800")
    axes[2].set_ylabel("Compression Ratio")
    axes[2].set_xlabel("Episode")
    axes[2].grid(True, alpha=0.3)

    # Phase transition markers
    prev_phase = phases[0] if phases else 0
    for i, phase in enumerate(phases):
        if phase != prev_phase:
            for ax in axes:
                ax.axvline(
                    x=episodes[i], color="red", linestyle="--",
                    alpha=0.5, linewidth=1,
                )
            axes[0].text(
                episodes[i], axes[0].get_ylim()[1] * 0.95,
                f"Phase {phase}", fontsize=8, color="red",
                ha="left", va="top",
            )
            prev_phase = phase

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info("Training curves saved to %s", output_path)

    if show:
        plt.show()
    plt.close()


def plot_compression_vs_accuracy(
    metrics_log: list[dict],
    output_path: str = "compression_accuracy.png",
) -> None:
    """
    Scatter plot: compression ratio vs accuracy.

    Color-coded by training phase.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use("Agg")
    except ImportError:
        logger.warning("matplotlib not installed")
        return

    accuracies = [m.get("accuracy", 0) for m in metrics_log]
    compressions = [m.get("compression_ratio", 0) for m in metrics_log]
    phases = [m.get("phase", 0) for m in metrics_log]

    phase_colors = {0: "#9E9E9E", 1: "#2196F3", 2: "#FF9800", 3: "#4CAF50"}

    fig, ax = plt.subplots(figsize=(8, 6))

    for phase_id in sorted(set(phases)):
        mask = [i for i, p in enumerate(phases) if p == phase_id]
        ax.scatter(
            [compressions[i] for i in mask],
            [accuracies[i] for i in mask],
            c=phase_colors.get(phase_id, "#000000"),
            alpha=0.3,
            s=10,
            label=f"Phase {phase_id}",
        )

    ax.set_xlabel("Compression Ratio (x)")
    ax.set_ylabel("Accuracy")
    ax.set_title("Compression vs Accuracy Tradeoff")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info("Compression vs accuracy plot saved to %s", output_path)
    plt.close()


def plot_token_distribution(
    token_ids_history: list[list[int]],
    vocab_size: int = 151936,
    top_k: int = 50,
    output_path: str = "token_distribution.png",
) -> None:
    """
    Plot the frequency distribution of protocol tokens.

    Shows which tokens the agents use most frequently in their
    learned protocol.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use("Agg")
    except ImportError:
        logger.warning("matplotlib not installed")
        return

    from collections import Counter

    # Count all tokens
    counter = Counter()
    for ids in token_ids_history:
        counter.update(ids)

    # Top-k
    top = counter.most_common(top_k)
    tokens, counts = zip(*top) if top else ([], [])

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(range(len(tokens)), counts, color="#2196F3", alpha=0.8)
    ax.set_xticks(range(len(tokens)))
    ax.set_xticklabels([str(t) for t in tokens], rotation=45, fontsize=7)
    ax.set_xlabel("Token ID")
    ax.set_ylabel("Frequency")
    ax.set_title(f"Top-{top_k} Protocol Tokens (total unique: {len(counter)})")
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info("Token distribution plot saved to %s", output_path)
    plt.close()


def plot_phase_summary(
    phase_history: list[dict],
    output_path: str = "phase_summary.png",
) -> None:
    """
    Bar chart comparing metrics across training phases.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use("Agg")
    except ImportError:
        logger.warning("matplotlib not installed")
        return

    if not phase_history:
        return

    names = [p.get("name", f"Phase {p.get('phase', '?')}") for p in phase_history]

    # Parse metric strings like "0.7500" to floats
    def parse_val(v):
        if isinstance(v, str):
            return float(v.replace("x", ""))
        return float(v)

    accs = [parse_val(p.get("avg_accuracy", 0)) for p in phase_history]
    comps = [parse_val(p.get("avg_compression", 0)) for p in phase_history]
    eps = [int(p.get("episodes", 0)) for p in phase_history]

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))

    axes[0].bar(names, accs, color="#4CAF50", alpha=0.8)
    axes[0].set_title("Avg Accuracy")
    axes[0].set_ylim(0, 1)

    axes[1].bar(names, comps, color="#FF9800", alpha=0.8)
    axes[1].set_title("Avg Compression (x)")

    axes[2].bar(names, eps, color="#2196F3", alpha=0.8)
    axes[2].set_title("Episodes")

    for ax in axes:
        ax.grid(True, alpha=0.3, axis="y")

    plt.suptitle("Phase Summary", fontsize=14)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    logger.info("Phase summary saved to %s", output_path)
    plt.close()


def generate_all_plots(
    metrics_log: list[dict],
    phase_history: list[dict],
    token_ids_history: Optional[list[list[int]]] = None,
    output_dir: str = "plots",
) -> None:
    """Generate all visualization plots."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    plot_training_curves(metrics_log, str(out / "training_curves.png"))
    plot_compression_vs_accuracy(metrics_log, str(out / "compression_accuracy.png"))
    plot_phase_summary(phase_history, str(out / "phase_summary.png"))

    if token_ids_history:
        plot_token_distribution(
            token_ids_history, output_path=str(out / "token_distribution.png")
        )

    logger.info("All plots saved to %s/", output_dir)
