"""Ser1es Platform — RunPod PHIREN Client

Handles dispatching PHIREN (hallucination guard) training jobs
to a RunPod Serverless endpoint.
"""

import httpx
import logging
import base64
from datetime import datetime, timezone

from .config import (
    RUNPOD_API_KEY,
    RUNPOD_PHIREN_ENDPOINT_ID,
    RUNPOD_API_BASE,
    RUNPOD_WEBHOOK_TOKEN,
    MODEL_HF_MAP,
    PHIREN_DATASET_MAP,
    PHIREN_MODEL_COSTS,
)

logger = logging.getLogger("phiren.runpod")


def _headers() -> dict:
    import os
    key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def dispatch_phiren_job(
    job_id: int,
    model: str,
    dataset: str,
    episodes: int,
    user_id: int,
    callback_url: str = "",
) -> dict:
    """Dispatch PHIREN training job to RunPod Serverless."""
    import os
    api_key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    endpoint_id = os.getenv("RUNPOD_PHIREN_ENDPOINT_ID", "") or RUNPOD_PHIREN_ENDPOINT_ID

    if not api_key:
        return {"error": "RUNPOD_API_KEY not configured"}
    if not endpoint_id:
        return {"error": "RUNPOD_PHIREN_ENDPOINT_ID not configured — PHIREN GPU endpoint not set up"}

    hf_model = MODEL_HF_MAP.get(model, model)
    dataset_info = PHIREN_DATASET_MAP.get(dataset, {"type": "local", "path": dataset})

    payload = {
        "input": {
            "job_id": job_id,
            "user_id": user_id,
            "product": "phiren",
            "model_id": hf_model,
            "model_key": model,
            "dataset": dataset_info,
            "dataset_id": dataset,
            "episodes": episodes,
            "callback_url": callback_url,
            "callback_token": os.getenv("RUNPOD_WEBHOOK_TOKEN", RUNPOD_WEBHOOK_TOKEN),
            # Hallucination guard LoRA config
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "learning_rate": 2e-5,
            "batch_size": 4,
            "gradient_accumulation_steps": 4,
            "warmup_ratio": 0.1,
            # MAPPO reward config for hallucination guard
            "reward_weights": {
                "factuality": 0.45,
                "calibration": 0.25,
                "helpfulness": 0.20,
                "robustness": 0.10,
            },
        }
    }

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/run"
        resp = httpx.post(url, json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"PHIREN RunPod job dispatched: job_id={job_id}, runpod_id={data.get('id')}")
        return data
    except httpx.HTTPStatusError as e:
        error_msg = f"RunPod PHIREN API error: {e.response.status_code} — {e.response.text}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"RunPod PHIREN dispatch failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


def check_phiren_status(runpod_request_id: str) -> dict:
    """Check PHIREN RunPod job status."""
    import os
    endpoint_id = os.getenv("RUNPOD_PHIREN_ENDPOINT_ID", "") or RUNPOD_PHIREN_ENDPOINT_ID
    if not endpoint_id:
        return {"status": "FAILED", "error": "RUNPOD_PHIREN_ENDPOINT_ID not configured"}

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/status/{runpod_request_id}"
        resp = httpx.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"PHIREN RunPod status check failed: {e}")
        return {"status": "UNKNOWN", "error": str(e)}


def cancel_phiren_job(runpod_request_id: str) -> dict:
    """Cancel a PHIREN RunPod job."""
    import os
    endpoint_id = os.getenv("RUNPOD_PHIREN_ENDPOINT_ID", "") or RUNPOD_PHIREN_ENDPOINT_ID
    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/cancel/{runpod_request_id}"
        resp = httpx.post(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"PHIREN RunPod cancel failed: {e}")
        return {"error": str(e)}


def process_completed_phiren_job(
    runpod_output: dict,
    job_id: int,
    user_id: int,
    model: str,
    db_session,
) -> dict:
    """Process completed PHIREN job: decode weights → encrypt to .phr → store."""
    from .database import PhirenTrainingJob, PhirenAdapter
    from .phiren_adapter import encrypt_and_store_phiren_adapter

    try:
        adapter_b64 = runpod_output.get("adapter_base64", "")
        if not adapter_b64:
            return {"error": "No adapter weights in RunPod output"}

        adapter_data = base64.b64decode(adapter_b64)
        if len(adapter_data) == 0:
            return {"error": "Empty adapter weights"}

        job = db_session.query(PhirenTrainingJob).filter(PhirenTrainingJob.id == job_id).first()
        if not job:
            return {"error": f"PhirenTrainingJob {job_id} not found"}

        metrics = runpod_output.get("metrics", {})
        factuality = metrics.get("factuality", 0.0)
        calibration = metrics.get("calibration", 0.0)

        model_label = PHIREN_MODEL_COSTS.get(model, {}).get("label", model)
        adapter_name = f"{model_label} Hallucination Guard #{job_id}"

        adapter = encrypt_and_store_phiren_adapter(
            adapter_data=adapter_data,
            user_id=user_id,
            job=job,
            adapter_name=adapter_name,
            db=db_session,
        )

        job.status = "completed"
        job.current_phase = "completed"
        job.current_episode = job.episodes
        job.factuality = factuality
        job.calibration = calibration
        job.completed_at = datetime.now(timezone.utc)

        db_session.commit()
        logger.info(f"PHIREN job {job_id} completed: adapter={adapter.id}, size={adapter.file_size}")

        return {
            "adapter_id": adapter.id,
            "adapter_name": adapter.name,
            "file_size": adapter.file_size,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Failed to process completed PHIREN job {job_id}: {e}")
        return {"error": str(e)}
