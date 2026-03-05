"""
server.py — OVISEN RunPod Worker Server

RunPod Serverless handler for OVISEN training jobs.
Receives training requests, runs MAPPO, uploads results.
"""

from __future__ import annotations

import json
import logging
import os
import traceback

logger = logging.getLogger(__name__)


def handler(event: dict) -> dict:
    """
    RunPod serverless handler.

    Expected input:
        {
            "model": "clip-vit-b32",
            "dataset": "imagenet-1k-sample",
            "episodes": 100,
            "job_id": "...",
            "webhook_url": "...",
        }
    """
    try:
        inp = event.get("input", {})
        model = inp.get("model", "clip-vit-b32")
        dataset = inp.get("dataset", "imagenet-1k-sample")
        episodes = inp.get("episodes", 100)
        job_id = inp.get("job_id", "unknown")

        logger.info(f"OVISEN training job {job_id}: {model} x {dataset} x {episodes} episodes")

        from ovisen_train.config import OVisenTrainConfig
        from ovisen_train.train import train

        config = OVisenTrainConfig(total_episodes=episodes)

        def progress_cb(ep, metrics):
            if ep % 10 == 0:
                logger.info(f"Progress: {ep}/{episodes} ({metrics.get('phase', '?')})")

        result = train(config, progress_callback=progress_cb)

        return {
            "status": "completed",
            "job_id": job_id,
            "fidelity": result.get("best_fidelity", 0),
            "compression_ratio": result.get("best_compression", 0),
        }

    except Exception as e:
        logger.error(f"Training failed: {e}\n{traceback.format_exc()}")
        return {
            "status": "failed",
            "error": str(e),
            "job_id": event.get("input", {}).get("job_id", "unknown"),
        }


if __name__ == "__main__":
    # Local testing
    test_event = {
        "input": {
            "model": "clip-vit-b32",
            "dataset": "imagenet-1k-sample",
            "episodes": 10,
            "job_id": "test-local",
        }
    }
    result = handler(test_event)
    print(json.dumps(result, indent=2))
