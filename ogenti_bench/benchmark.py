"""
benchmark.py — Ogenti Protocol Benchmark Suite

Runs standardized benchmarks against trained encoder/decoder pairs.
Produces a BenchmarkReport with all key metrics.

Usage
-----
  python -m ogenti_bench.benchmark --encoder path/to/encoder --decoder path/to/decoder
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Optional

from ogenti_core.encoder import OgentiEncoder
from ogenti_core.decoder import OgentiDecoder
from ogenti_core.protocol import ProtocolConfig
from ogenti_core.channel import CommunicationChannel

from ogenti_train.environment import TaskGenerator, TaskCategory
from ogenti_train.rewards import reward_accuracy

from ogenti_bench.metrics import (
    BenchmarkReport,
    compression_ratio,
    semantic_fidelity,
    protocol_stability,
    throughput,
    token_budget_utilization,
)

logger = logging.getLogger(__name__)


class OgentiBenchmark:
    """
    Standardized benchmark for evaluating Ogenti protocol quality.

    Runs a trained encoder→decoder pipeline against a suite of tasks
    and collects metrics.
    """

    def __init__(
        self,
        encoder: OgentiEncoder,
        decoder: OgentiDecoder,
        protocol_config: Optional[ProtocolConfig] = None,
        task_generator: Optional[TaskGenerator] = None,
        num_episodes: int = 500,
    ):
        self.encoder = encoder
        self.decoder = decoder
        self.protocol_config = protocol_config or ProtocolConfig()
        self.task_gen = task_generator or TaskGenerator(phase=3)  # All categories
        self.num_episodes = num_episodes

    def run(self) -> BenchmarkReport:
        """Run the full benchmark suite."""
        logger.info("Running Ogenti benchmark (%d episodes)...", self.num_episodes)
        start = time.time()

        original_tokens_list = []
        protocol_tokens_list = []
        decoded_texts = []
        references = []
        accuracies = []
        budgets = []

        channel = CommunicationChannel(self.protocol_config)

        for i in range(self.num_episodes):
            task = self.task_gen.sample_one()

            # Encode
            orig_count = len(self.encoder.tokenizer.encode(task.instruction))
            message = self.encoder.encode(
                task.instruction,
                sender_id="bench_encoder",
            )
            proto_count = message.token_count

            # Decode
            action = self.decoder.decode(message)

            # Accuracy
            acc = reward_accuracy(action.text, task.reference)

            original_tokens_list.append(orig_count)
            protocol_tokens_list.append(proto_count)
            decoded_texts.append(action.text)
            references.append(task.reference)
            accuracies.append(acc)
            budgets.append(self.protocol_config.max_message_tokens)

            if (i + 1) % 100 == 0:
                logger.info("  ... %d/%d episodes", i + 1, self.num_episodes)

        elapsed = time.time() - start

        # Build report
        report = BenchmarkReport(
            total_episodes=self.num_episodes,
            total_time_s=elapsed,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        report.add(compression_ratio(original_tokens_list, protocol_tokens_list))
        report.add(semantic_fidelity(decoded_texts, references))
        report.add(protocol_stability(accuracies))
        report.add(throughput(self.num_episodes, elapsed))
        report.add(token_budget_utilization(protocol_tokens_list, budgets))

        # Per-category breakdown
        per_cat = self._per_category_breakdown(
            decoded_texts, references, accuracies,
            [self.task_gen.sample_one().category for _ in range(self.num_episodes)],
        )
        for cat_name, cat_acc in per_cat.items():
            from ogenti_bench.metrics import MetricResult
            report.add(MetricResult(
                f"accuracy/{cat_name}",
                cat_acc,
            ))

        logger.info("\n%s", report.pretty())
        return report

    def _per_category_breakdown(
        self,
        decoded: list[str],
        refs: list[str],
        accs: list[float],
        categories: list[TaskCategory],
    ) -> dict[str, float]:
        """Compute accuracy per task category."""
        from collections import defaultdict
        cat_accs = defaultdict(list)
        for acc, cat in zip(accs, categories):
            cat_accs[cat.value].append(acc)
        return {
            cat: sum(vals) / len(vals)
            for cat, vals in cat_accs.items()
            if vals
        }

    def run_cross_compatibility(
        self,
        encoder_b: OgentiEncoder,
        decoder_b: OgentiDecoder,
        num_episodes: int = 100,
    ) -> BenchmarkReport:
        """
        Test cross-agent compatibility.

        Pairs encoder_A with decoder_B and vice versa.
        """
        logger.info("Running cross-compatibility test...")

        native_accs = []
        cross_accs_ab = []
        cross_accs_ba = []

        for _ in range(num_episodes):
            task = self.task_gen.sample_one()

            # Native: encoder_A → decoder_A
            msg_a = self.encoder.encode(task.instruction)
            act_a = self.decoder.decode(msg_a)
            native_accs.append(reward_accuracy(act_a.text, task.reference))

            # Cross: encoder_A → decoder_B
            act_ab = decoder_b.decode(msg_a)
            cross_accs_ab.append(reward_accuracy(act_ab.text, task.reference))

            # Cross: encoder_B → decoder_A
            msg_b = encoder_b.encode(task.instruction)
            act_ba = self.decoder.decode(msg_b)
            cross_accs_ba.append(reward_accuracy(act_ba.text, task.reference))

        report = BenchmarkReport(total_episodes=num_episodes)

        from ogenti_bench.metrics import cross_agent_compatibility, MetricResult
        report.add(cross_agent_compatibility(native_accs, cross_accs_ab))

        avg_native = sum(native_accs) / len(native_accs)
        avg_cross = (sum(cross_accs_ab) + sum(cross_accs_ba)) / (2 * num_episodes)

        report.add(MetricResult("native_accuracy", avg_native))
        report.add(MetricResult("cross_accuracy_avg", avg_cross))

        logger.info("\n%s", report.pretty())
        return report


# ─────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ogenti Benchmark")
    parser.add_argument("--encoder", type=str, required=True, help="Encoder checkpoint path")
    parser.add_argument("--decoder", type=str, required=True, help="Decoder checkpoint path")
    parser.add_argument("--episodes", type=int, default=500, help="Number of episodes")
    parser.add_argument("--output", type=str, default=None, help="Save report JSON to path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    encoder = OgentiEncoder.from_pretrained(args.encoder)
    decoder = OgentiDecoder.from_pretrained(args.decoder)

    bench = OgentiBenchmark(encoder, decoder, num_episodes=args.episodes)
    report = bench.run()

    if args.output:
        import json
        with open(args.output, "w") as f:
            json.dump(report.summary(), f, indent=2)
        logger.info("Report saved to %s", args.output)


if __name__ == "__main__":
    main()
