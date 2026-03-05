"""Series Platform -- RunPod MURHEN Client

Handles dispatching MURHEN (position-agnostic recall / lost-in-the-middle fix)
training jobs to a RunPod Serverless endpoint.
"""

import httpx
import logging
import base64
from datetime import datetime, timezone

from .config import (
    RUNPOD_API_KEY,
    RUNPOD_MURHEN_ENDPOINT_ID,
    RUNPOD_API_BASE,
    RUNPOD_WEBHOOK_TOKEN,
    MODEL_HF_MAP,
    MURHEN_DATASET_MAP,
    MURHEN_MODEL_COSTS,
)

logger = logging.getLogger("murhen.runpod")


def _headers() -> dict:
    import os
    key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def dispatch_murhen_job(
    job_id: int,
    model: str,
    dataset: str,
    episodes: int,
    user_id: int,
    callback_url: str = "",
) -> dict:
    """Dispatch MURHEN training job to RunPod Serverless."""
    import os
    api_key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    endpoint_id = os.getenv("RUNPOD_MURHEN_ENDPOINT_ID", "") or RUNPOD_MURHEN_ENDPOINT_ID

    if not api_key:
        return {"error": "RUNPOD_API_KEY not configured"}
    if not endpoint_id:
        return {"error": "RUNPOD_MURHEN_ENDPOINT_ID not configured -- MURHEN GPU endpoint not set up"}

    hf_model = MODEL_HF_MAP.get(model, model)
    dataset_info = MURHEN_DATASET_MAP.get(dataset, {"type": "local", "path": dataset})

    payload = {
        "input": {
            "job_id": job_id,
            "user_id": user_id,
            "product": "murhen",
            "model_id": hf_model,
            "model_key": model,
            "dataset": dataset_info,
            "dataset_id": dataset,
            "episodes": episodes,
            "callback_url": callback_url,
            "callback_token": os.getenv("RUNPOD_WEBHOOK_TOKEN", RUNPOD_WEBHOOK_TOKEN),
            # Position-agnostic recall LoRA config
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "learning_rate": 2e-5,
            "batch_size": 4,
            "gradient_accumulation_steps": 4,
            "warmup_ratio": 0.1,
            # MAPPO reward config for position-agnostic recall
            "reward_weights": {
                "recall": 0.35,
                "uniformity": 0.30,
                "synthesis": 0.20,
                "robustness": 0.15,
            },
        }
    }

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/run"
        resp = httpx.post(url, json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"MURHEN RunPod job dispatched: job_id={job_id}, runpod_id={data.get('id')}")
        return data
    except httpx.HTTPStatusError as e:
        error_msg = f"RunPod MURHEN API error: {e.response.status_code} -- {e.response.text}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"RunPod MURHEN dispatch failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


def check_murhen_status(runpod_request_id: str) -> dict:
    """Check MURHEN RunPod job status."""
    import os
    endpoint_id = os.getenv("RUNPOD_MURHEN_ENDPOINT_ID", "") or RUNPOD_MURHEN_ENDPOINT_ID
    if not endpoint_id:
        return {"status": "FAILED", "error": "RUNPOD_MURHEN_ENDPOINT_ID not configured"}

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/status/{runpod_request_id}"
        resp = httpx.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"MURHEN RunPod status check failed: {e}")
        return {"status": "UNKNOWN", "error": str(e)}


def cancel_murhen_job(runpod_request_id: str) -> dict:
    """Cancel a MURHEN RunPod job."""
    import os
    endpoint_id = os.getenv("RUNPOD_MURHEN_ENDPOINT_ID", "") or RUNPOD_MURHEN_ENDPOINT_ID
    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/cancel/{runpod_request_id}"
        resp = httpx.post(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"MURHEN RunPod cancel failed: {e}")
        return {"error": str(e)}


def process_completed_murhen_job(
    runpod_output: dict,
    job_id: int,
    user_id: int,
    model: str,
    db_session,
) -> dict:
    """Process completed MURHEN job: decode weights -> encrypt to .mrh -> store."""
    from .database import MurhenTrainingJob, MurhenAdapter
    from .murhen_adapter import encrypt_and_store_murhen_adapter

    try:
        adapter_b64 = runpod_output.get("adapter_base64", "")
        if not adapter_b64:
            return {"error": "No adapter weights in RunPod output"}

        adapter_data = base64.b64decode(adapter_b64)
        if len(adapter_data) == 0:
            return {"error": "Empty adapter weights"}

        job = db_session.query(MurhenTrainingJob).filter(MurhenTrainingJob.id == job_id).first()
        if not job:
            return {"error": f"MurhenTrainingJob {job_id} not found"}

        metrics = runpod_output.get("metrics", {})
        recall_rate = metrics.get("recall_rate", 0.0)
        position_uniformity = metrics.get("position_uniformity", 0.0)

        model_label = MURHEN_MODEL_COSTS.get(model, {}).get("label", model)
        adapter_name = f"{model_label} Position-Agnostic Recall #{job_id}"

        adapter = encrypt_and_store_murhen_adapter(
            adapter_data=adapter_data,
            user_id=user_id,
            job=job,
            adapter_name=adapter_name,
            db=db_session,
        )

        job.status = "completed"
        job.current_phase = "completed"
        job.current_episode = job.episodes
        job.recall_rate = recall_rate
        job.position_uniformity = position_uniformity
        job.completed_at = datetime.now(timezone.utc)

        db_session.commit()
        logger.info(f"MURHEN job {job_id} completed: adapter={adapter.id}, size={adapter.file_size}")

        return {
            "adapter_id": adapter.id,
            "adapter_name": adapter.name,
            "file_size": adapter.file_size,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Failed to process completed MURHEN job {job_id}: {e}")
        return {"error": str(e)}
