"""Ser1es Platform -- RunPod S-SER1ES Client

Handles dispatching S-SER1ES (Neural Surgery / Selective RL) training jobs
to a RunPod Serverless endpoint.
"""

import httpx
import logging
import base64
from datetime import datetime, timezone

from .config import (
    RUNPOD_API_KEY,
    RUNPOD_SSERIES_ENDPOINT_ID,
    RUNPOD_API_BASE,
    RUNPOD_WEBHOOK_TOKEN,
    MODEL_HF_MAP,
    SSERIES_DATASET_MAP,
    SSERIES_MODEL_COSTS,
)

logger = logging.getLogger("sseries.runpod")


def _headers() -> dict:
    import os
    key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def dispatch_sseries_job(
    job_id: int,
    model: str,
    dataset: str,
    episodes: int,
    user_id: int,
    callback_url: str = "",
) -> dict:
    """Dispatch S-SER1ES neural surgery job to RunPod Serverless."""
    import os
    api_key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    endpoint_id = os.getenv("RUNPOD_SSERIES_ENDPOINT_ID", "") or RUNPOD_SSERIES_ENDPOINT_ID

    if not api_key:
        return {"error": "RUNPOD_API_KEY not configured"}
    if not endpoint_id:
        return {"error": "RUNPOD_SSERIES_ENDPOINT_ID not configured -- S-SER1ES GPU endpoint not set up"}

    hf_model = MODEL_HF_MAP.get(model, model)
    dataset_info = SSERIES_DATASET_MAP.get(dataset, {"type": "local", "path": dataset})

    payload = {
        "input": {
            "job_id": job_id,
            "user_id": user_id,
            "product": "sseries",
            "model_id": hf_model,
            "model_key": model,
            "dataset": dataset_info,
            "dataset_id": dataset,
            "episodes": episodes,
            "callback_url": callback_url,
            "callback_token": os.getenv("RUNPOD_WEBHOOK_TOKEN", RUNPOD_WEBHOOK_TOKEN),
            # Neural Surgery Selective RL config
            "surgery_method": "masked_dpo",
            "blame_threshold": 0.85,
            "surgery_budget_pct": 1.0,
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "learning_rate": 2e-5,
            "batch_size": 4,
            "gradient_accumulation_steps": 4,
            "warmup_ratio": 0.1,
            "dpo_beta": 0.1,
            "max_param_distance": 0.5,
            "anti_forgetting_kl_limit": 0.05,
            # Blame attribution weights
            "blame_weights": {
                "gradient": 0.40,
                "activation": 0.30,
                "consistency": 0.30,
            },
        }
    }

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/run"
        resp = httpx.post(url, json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"S-SER1ES RunPod job dispatched: job_id={job_id}, runpod_id={data.get('id')}")
        return data
    except httpx.HTTPStatusError as e:
        error_msg = f"RunPod S-SER1ES API error: {e.response.status_code} -- {e.response.text}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"RunPod S-SER1ES dispatch failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


def check_sseries_status(runpod_request_id: str) -> dict:
    """Check S-SER1ES RunPod job status."""
    import os
    endpoint_id = os.getenv("RUNPOD_SSERIES_ENDPOINT_ID", "") or RUNPOD_SSERIES_ENDPOINT_ID
    if not endpoint_id:
        return {"status": "FAILED", "error": "RUNPOD_SSERIES_ENDPOINT_ID not configured"}

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/status/{runpod_request_id}"
        resp = httpx.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"S-SER1ES RunPod status check failed: {e}")
        return {"status": "UNKNOWN", "error": str(e)}


def cancel_sseries_job(runpod_request_id: str) -> dict:
    """Cancel an S-SER1ES RunPod job."""
    import os
    endpoint_id = os.getenv("RUNPOD_SSERIES_ENDPOINT_ID", "") or RUNPOD_SSERIES_ENDPOINT_ID
    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/cancel/{runpod_request_id}"
        resp = httpx.post(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"S-SER1ES RunPod cancel failed: {e}")
        return {"error": str(e)}


def process_completed_sseries_job(
    runpod_output: dict,
    job_id: int,
    user_id: int,
    model: str,
    db_session,
) -> dict:
    """Process completed S-SER1ES job: decode weights -> encrypt to .srs -> store."""
    from .database import SseriesTrainingJob, SseriesAdapter
    from .sseries_adapter import encrypt_and_store_sseries_adapter

    try:
        adapter_b64 = runpod_output.get("adapter_base64", "")
        if not adapter_b64:
            return {"error": "No adapter weights in RunPod output"}

        adapter_data = base64.b64decode(adapter_b64)
        if len(adapter_data) == 0:
            return {"error": "Empty adapter weights"}

        job = db_session.query(SseriesTrainingJob).filter(SseriesTrainingJob.id == job_id).first()
        if not job:
            return {"error": f"S-SER1ES Job {job_id} not found"}

        metrics = runpod_output.get("metrics", {})
        job.neuron_efficiency = metrics.get("neuron_efficiency", 0.0)
        job.surgery_precision = metrics.get("surgery_precision", 0.0)
        job.current_phase = "completed"
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)

        model_label = SSERIES_MODEL_COSTS.get(model, {}).get("label", model)
        adapter_name = f"{model_label} Neural Surgery #{job_id}"

        adapter = encrypt_and_store_sseries_adapter(
            adapter_data=adapter_data,
            user_id=user_id,
            job=job,
            adapter_name=adapter_name,
            db=db_session,
        )

        db_session.commit()
        return {"adapter_id": adapter.id, "name": adapter.name, "file_size": adapter.file_size}

    except Exception as e:
        logger.error(f"S-SER1ES post-processing failed: {e}")
        return {"error": str(e)}
