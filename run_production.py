#!/usr/bin/env python3
"""
run_production.py — Ogenti Production Training Launcher

Starts the full training pipeline with live dashboard monitoring.
Designed for GPU servers (RunPod, Lambda, etc.) with A100/H100.

Usage:
  # Default (50K episodes, Qwen2.5-3B, live dashboard on :8000)
  python run_production.py

  # Custom config
  python run_production.py --config configs/production.json

  # Quick test run (100 episodes, no wandb)
  python run_production.py --quick

  # Headless (no dashboard server)
  python run_production.py --headless

Architecture:
  ┌─────────────────────┐
  │   OgentiTrainer     │──── TrainerBridge ────┐
  │   (GPU thread)      │     (thread-safe)     │
  │                     │                       ▼
  │  Qwen2.5-3B + LoRA  │            ┌──────────────────┐
  │  MAPPO · 5 Phases   │            │  FastAPI Server   │
  │  KD → Adapter       │            │  WebSocket + REST │
  └─────────────────────┘            │  :8000            │
                                     └──────────────────┘
                                              │
                                     ┌────────▼────────┐
                                     │  ogenti.com     │
                                     │  Live Dashboard │
                                     └─────────────────┘
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

logger = logging.getLogger("ogenti.production")


# Force UTF-8 on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def check_environment() -> dict:
    """Pre-flight checks before launching training."""
    import torch

    info = {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "cuda": torch.cuda.is_available(),
        "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "gpu_name": "",
        "gpu_memory_gb": 0,
    }

    if info["cuda"] and info["gpu_count"] > 0:
        info["gpu_name"] = torch.cuda.get_device_name(0)
        info["gpu_memory_gb"] = round(
            torch.cuda.get_device_properties(0).total_memory / 1e9, 1
        )

    return info


def print_banner(info: dict, config) -> None:
    """Print a beautiful startup banner."""
    gpu_str = (
        f"{info['gpu_count']}× {info['gpu_name']} ({info['gpu_memory_gb']}GB)"
        if info["cuda"]
        else "CPU only (not recommended)"
    )

    print(
        f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║       ◆  O G E N T I  —  Production Training  ◆             ║
║       AI Telepathy Protocol                                ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Model:      {config.encoder.model_name:<44s}║
║  LoRA:       rank={config.encoder.lora_rank}, α={str(config.encoder.lora_alpha):<35s}║
║  Episodes:   {config.total_episodes:<44,d}║
║  Phases:     {len(config.phases)} (warmup → simple → complex → gen → universal)  ║
║  GPU:        {gpu_str:<44s}║
║  Precision:  {config.infra.mixed_precision:<44s}║
║  DeepSpeed:  ZeRO-{config.infra.deepspeed_stage:<41d}║
║  W&B:        {str(config.infra.use_wandb):<44s}║
║                                                              ║
║  Python:     {info['python']:<44s}║
║  PyTorch:    {info['torch']:<44s}║
║  CUDA:       {str(info['cuda']):<44s}║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    )


def main():
    parser = argparse.ArgumentParser(
        description="Ogenti Production Training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to training config JSON (default: configs/production.json)",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick test: 100 episodes, no W&B, fast phases",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="No dashboard server (training only)",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Dashboard server port (default: 8000)",
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0",
        help="Dashboard server bind host",
    )
    parser.add_argument(
        "--resume", type=str, default=None,
        help="Resume from checkpoint directory",
    )
    parser.add_argument(
        "--no-wandb", action="store_true",
        help="Disable Weights & Biases logging",
    )
    parser.add_argument(
        "--dataset", type=str, default=None,
        help="Path to training dataset (JSONL)",
    )
    args = parser.parse_args()

    # ── Logging ──
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("training.log", mode="a", encoding="utf-8"),
        ],
    )

    # ── Environment check ──
    logger.info("Running pre-flight checks...")
    info = check_environment()

    if not info["cuda"]:
        logger.warning(
            "No CUDA GPU detected! Training will be extremely slow on CPU. "
            "Consider using RunPod, Lambda Labs, or another GPU provider."
        )

    # ── Load config ──
    from ogenti_train.config import TrainConfig

    config_path = args.config
    if config_path is None:
        default_config = Path("configs/production.json")
        if default_config.exists():
            config_path = str(default_config)

    if config_path:
        logger.info("Loading config: %s", config_path)
        config = TrainConfig.load(config_path)
    else:
        logger.info("Using default config")
        config = TrainConfig()

    # ── Apply overrides ──
    if args.quick:
        config.total_episodes = 100
        config.infra.use_wandb = False
        config.infra.log_every = 5
        config.infra.checkpoint_every = 50
        config.eval_every = 25
        config.eval_episodes = 5
        # Shorten all phases
        for phase in config.phases:
            phase.max_episodes = 25
            phase.min_episodes = 10
        # CPU: auto-switch to smaller model
        if not info["cuda"]:
            small_model = "Qwen/Qwen2.5-0.5B-Instruct"
            logger.info("CPU detected: switching to %s for faster testing", small_model)
            config.encoder.model_name = small_model
            config.decoder.model_name = small_model
            config.encoder.dtype = "float32"
            config.decoder.dtype = "float32"
            config.encoder.device = "cpu"
            config.decoder.device = "cpu"
            config.infra.mixed_precision = "no"
        logger.info("Quick test mode: 100 episodes, shortened phases")

    if args.no_wandb:
        config.infra.use_wandb = False

    if args.dataset:
        config.dataset_path = args.dataset

    # Auto-detect dataset
    if config.dataset_path is None:
        for candidate in ["data/train.jsonl", "data/ogenti_tasks.jsonl"]:
            if Path(candidate).exists():
                config.dataset_path = candidate
                logger.info("Auto-detected dataset: %s", candidate)
                break

    # ── Banner ──
    print_banner(info, config)

    # ── Start dashboard server ──
    bridge = None
    if not args.headless:
        from ogenti_train.server import TrainerBridge, start_server_background

        bridge = TrainerBridge()
        server_thread = start_server_background(
            bridge, host=args.host, port=args.port
        )
        logger.info(
            "═══ Live Dashboard: http://%s:%d ═══",
            "localhost" if args.host == "0.0.0.0" else args.host,
            args.port,
        )
        time.sleep(1)  # Let server fully start

    # ── Signal handler for graceful shutdown ──
    _shutdown = False

    def handle_signal(sig, frame):
        nonlocal _shutdown
        if _shutdown:
            logger.warning("Force quit.")
            sys.exit(1)
        _shutdown = True
        logger.info("Graceful shutdown requested (Ctrl+C again to force)...")
        if bridge:
            bridge.on_training_end({"reason": "interrupted"})

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    # ── Launch training ──
    from ogenti_train.train import OgentiTrainer

    trainer = OgentiTrainer(config, bridge=bridge)
    trainer.setup()

    # Resume from checkpoint if requested
    if args.resume:
        trainer.load_checkpoint(args.resume)

    logger.info("═══ Starting training loop ═══")
    start = time.time()

    try:
        trainer.train()
    except KeyboardInterrupt:
        logger.info("Training interrupted by user.")
    except Exception as e:
        logger.exception("Training failed: %s", e)
        if bridge:
            bridge.on_training_end({"reason": "error", "error": str(e)})
        raise

    elapsed = time.time() - start
    logger.info(
        "═══ Done. %d episodes in %.1f min (%.1f ep/s) ═══",
        trainer.global_episode,
        elapsed / 60,
        trainer.global_episode / elapsed if elapsed > 0 else 0,
    )

    # Keep server alive for dashboard viewing after training completes
    if not args.headless and bridge:
        logger.info("Training complete. Dashboard still live at http://localhost:%d", args.port)
        logger.info("Press Ctrl+C to shutdown.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    logger.info("Goodbye.")


if __name__ == "__main__":
    main()
