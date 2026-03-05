"""Series Platform -- RunPod PARHEN Client

Handles dispatching PARHEN (anti-sycophancy) training jobs
to a RunPod Serverless endpoint.
"""

import httpx
import logging
import base64
from datetime import datetime, timezone

from .config import (
    RUNPOD_API_KEY,
    RUNPOD_PARHEN_ENDPOINT_ID,
    RUNPOD_API_BASE,
    RUNPOD_WEBHOOK_TOKEN,
    MODEL_HF_MAP,
    PARHEN_DATASET_MAP,
    PARHEN_MODEL_COSTS,
)

logger = logging.getLogger("parhen.runpod")


def _headers() -> dict:
    import os
    key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def dispatch_parhen_job(
    job_id: int,
    model: str,
    dataset: str,
    episodes: int,
    user_id: int,
    callback_url: str = "",
) -> dict:
    """Dispatch PARHEN training job to RunPod Serverless."""
    import os
    api_key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    endpoint_id = os.getenv("RUNPOD_PARHEN_ENDPOINT_ID", "") or RUNPOD_PARHEN_ENDPOINT_ID

    if not api_key:
        return {"error": "RUNPOD_API_KEY not configured"}
    if not endpoint_id:
        return {"error": "RUNPOD_PARHEN_ENDPOINT_ID not configured -- PARHEN GPU endpoint not set up"}

    hf_model = MODEL_HF_MAP.get(model, model)
    dataset_info = PARHEN_DATASET_MAP.get(dataset, {"type": "local", "path": dataset})

    payload = {
        "input": {
            "job_id": job_id,
            "user_id": user_id,
            "product": "parhen",
            "model_id": hf_model,
            "model_key": model,
            "dataset": dataset_info,
            "dataset_id": dataset,
            "episodes": episodes,
            "callback_url": callback_url,
            "callback_token": os.getenv("RUNPOD_WEBHOOK_TOKEN", RUNPOD_WEBHOOK_TOKEN),
            # Anti-sycophancy LoRA config
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "learning_rate": 2e-5,
            "batch_size": 4,
            "gradient_accumulation_steps": 4,
            "warmup_ratio": 0.1,
            # MAPPO reward config for anti-sycophancy
            "reward_weights": {
                "consistency": 0.35,
                "independence": 0.25,
                "updatability": 0.25,
                "quality": 0.15,
            },
        }
    }

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/run"
        resp = httpx.post(url, json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"PARHEN RunPod job dispatched: job_id={job_id}, runpod_id={data.get('id')}")
        return data
    except httpx.HTTPStatusError as e:
        error_msg = f"RunPod PARHEN API error: {e.response.status_code} -- {e.response.text}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"RunPod PARHEN dispatch failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


def check_parhen_status(runpod_request_id: str) -> dict:
    """Check PARHEN RunPod job status."""
    import os
    endpoint_id = os.getenv("RUNPOD_PARHEN_ENDPOINT_ID", "") or RUNPOD_PARHEN_ENDPOINT_ID
    if not endpoint_id:
        return {"status": "FAILED", "error": "RUNPOD_PARHEN_ENDPOINT_ID not configured"}

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/status/{runpod_request_id}"
        resp = httpx.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"PARHEN RunPod status check failed: {e}")
        return {"status": "UNKNOWN", "error": str(e)}


def cancel_parhen_job(runpod_request_id: str) -> dict:
    """Cancel a PARHEN RunPod job."""
    import os
    endpoint_id = os.getenv("RUNPOD_PARHEN_ENDPOINT_ID", "") or RUNPOD_PARHEN_ENDPOINT_ID
    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/cancel/{runpod_request_id}"
        resp = httpx.post(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"PARHEN RunPod cancel failed: {e}")
        return {"error": str(e)}


def process_completed_parhen_job(
    runpod_output: dict,
    job_id: int,
    user_id: int,
    model: str,
    db_session,
) -> dict:
    """Process completed PARHEN job: decode weights -> encrypt to .prh -> store."""
    from .database import ParhenTrainingJob, ParhenAdapter
    from .parhen_adapter import encrypt_and_store_parhen_adapter

    try:
        adapter_b64 = runpod_output.get("adapter_base64", "")
        if not adapter_b64:
            return {"error": "No adapter weights in RunPod output"}

        adapter_data = base64.b64decode(adapter_b64)
        if len(adapter_data) == 0:
            return {"error": "Empty adapter weights"}

        job = db_session.query(ParhenTrainingJob).filter(ParhenTrainingJob.id == job_id).first()
        if not job:
            return {"error": f"ParhenTrainingJob {job_id} not found"}

        metrics = runpod_output.get("metrics", {})
        conviction = metrics.get("conviction", 0.0)
        independence = metrics.get("independence", 0.0)

        model_label = PARHEN_MODEL_COSTS.get(model, {}).get("label", model)
        adapter_name = f"{model_label} Anti-Sycophancy Guard #{job_id}"

        adapter = encrypt_and_store_parhen_adapter(
            adapter_data=adapter_data,
            user_id=user_id,
            job=job,
            adapter_name=adapter_name,
            db=db_session,
        )

        job.status = "completed"
        job.current_phase = "completed"
        job.current_episode = job.episodes
        job.conviction = conviction
        job.independence = independence
        job.completed_at = datetime.now(timezone.utc)

        db_session.commit()
        logger.info(f"PARHEN job {job_id} completed: adapter={adapter.id}, size={adapter.file_size}")

        return {
            "adapter_id": adapter.id,
            "adapter_name": adapter.name,
            "file_size": adapter.file_size,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Failed to process completed PARHEN job {job_id}: {e}")
        return {"error": str(e)}
