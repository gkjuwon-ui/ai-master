"""O Series Platform — RunPod OVISEN Client

Handles dispatching OVISEN (image embedding compression) training jobs
to a separate RunPod Serverless endpoint for vision model training.
"""

import httpx
import logging
import base64
from datetime import datetime, timezone

from .config import (
    RUNPOD_API_KEY,
    RUNPOD_OVISEN_ENDPOINT_ID,
    RUNPOD_API_BASE,
    RUNPOD_WEBHOOK_TOKEN,
    OVISEN_MODEL_HF_MAP,
    OVISEN_DATASET_MAP,
    OVISEN_MODEL_COSTS,
)

logger = logging.getLogger("ovisen.runpod")


def _headers() -> dict:
    import os
    key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _ovisen_endpoint_url(path: str = "") -> str:
    import os
    eid = os.getenv("RUNPOD_OVISEN_ENDPOINT_ID", "") or RUNPOD_OVISEN_ENDPOINT_ID
    return f"{RUNPOD_API_BASE}/{eid}{path}"


def dispatch_ovisen_job(
    job_id: int,
    model: str,
    dataset: str,
    episodes: int,
    user_id: int,
    callback_url: str = "",
) -> dict:
    """Dispatch OVISEN training job to RunPod Serverless."""
    import os
    api_key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    endpoint_id = os.getenv("RUNPOD_OVISEN_ENDPOINT_ID", "") or RUNPOD_OVISEN_ENDPOINT_ID

    if not api_key:
        return {"error": "RUNPOD_API_KEY not configured"}
    if not endpoint_id:
        return {"error": "RUNPOD_OVISEN_ENDPOINT_ID not configured — OVISEN GPU endpoint not set up"}

    hf_model = OVISEN_MODEL_HF_MAP.get(model, model)
    dataset_info = OVISEN_DATASET_MAP.get(dataset, {"type": "local", "path": dataset})

    payload = {
        "input": {
            "job_id": job_id,
            "user_id": user_id,
            "product": "ovisen",
            "model_id": hf_model,
            "model_key": model,
            "dataset": dataset_info,
            "dataset_id": dataset,
            "episodes": episodes,
            "callback_url": callback_url,
            "callback_token": os.getenv("RUNPOD_WEBHOOK_TOKEN", RUNPOD_WEBHOOK_TOKEN),
            # Vision-specific LoRA config
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "learning_rate": 1e-4,
            "batch_size": 8,
            "gradient_accumulation_steps": 2,
            "warmup_ratio": 0.05,
            "image_size": 224,
            "embedding_dim": 256,
            # MARL reward config for image compression
            "reward_weights": {
                "reconstruction_fidelity": 0.4,  # SSIM/LPIPS score
                "compression_ratio": 0.3,         # how much smaller
                "embedding_usefulness": 0.2,       # downstream task accuracy
                "latency": 0.1,                    # inference speed
            },
        }
    }

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/run"
        resp = httpx.post(url, json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"OVISEN RunPod job dispatched: job_id={job_id}, runpod_id={data.get('id')}")
        return data
    except httpx.HTTPStatusError as e:
        error_msg = f"RunPod OVISEN API error: {e.response.status_code} — {e.response.text}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"RunPod OVISEN dispatch failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


def check_ovisen_status(runpod_request_id: str) -> dict:
    """Check OVISEN RunPod job status."""
    import os
    endpoint_id = os.getenv("RUNPOD_OVISEN_ENDPOINT_ID", "") or RUNPOD_OVISEN_ENDPOINT_ID
    if not endpoint_id:
        return {"status": "FAILED", "error": "RUNPOD_OVISEN_ENDPOINT_ID not configured"}

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/status/{runpod_request_id}"
        resp = httpx.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"OVISEN RunPod status check failed: {e}")
        return {"status": "UNKNOWN", "error": str(e)}


def cancel_ovisen_job(runpod_request_id: str) -> dict:
    """Cancel an OVISEN RunPod job."""
    import os
    endpoint_id = os.getenv("RUNPOD_OVISEN_ENDPOINT_ID", "") or RUNPOD_OVISEN_ENDPOINT_ID
    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/cancel/{runpod_request_id}"
        resp = httpx.post(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"OVISEN RunPod cancel failed: {e}")
        return {"error": str(e)}


def process_completed_ovisen_job(
    runpod_output: dict,
    job_id: int,
    user_id: int,
    model: str,
    db_session,
) -> dict:
    """Process completed OVISEN job: decode weights → encrypt to .oge → store."""
    from .database import OVisenTrainingJob, OVisenAdapter
    from .ovisen_adapter import encrypt_and_store_ovisen_adapter

    try:
        adapter_b64 = runpod_output.get("adapter_base64", "")
        if not adapter_b64:
            return {"error": "No adapter weights in RunPod output"}

        adapter_data = base64.b64decode(adapter_b64)
        if len(adapter_data) == 0:
            return {"error": "Empty adapter weights"}

        job = db_session.query(OVisenTrainingJob).filter(OVisenTrainingJob.id == job_id).first()
        if not job:
            return {"error": f"OVisenTrainingJob {job_id} not found"}

        metrics = runpod_output.get("metrics", {})
        fidelity = metrics.get("fidelity", 0.0)
        compression = metrics.get("compression", 0.0)

        model_label = OVISEN_MODEL_COSTS.get(model, {}).get("label", model)
        adapter_name = f"{model_label} Vision Adapter #{job_id}"

        adapter = encrypt_and_store_ovisen_adapter(
            adapter_data=adapter_data,
            user_id=user_id,
            job=job,
            adapter_name=adapter_name,
            db=db_session,
        )

        job.status = "completed"
        job.current_phase = "completed"
        job.current_episode = job.episodes
        job.fidelity = fidelity
        job.compression = compression
        job.completed_at = datetime.now(timezone.utc)

        db_session.commit()
        logger.info(f"OVISEN job {job_id} completed: adapter={adapter.id}, size={adapter.file_size}")

        return {
            "adapter_id": adapter.id,
            "adapter_name": adapter.name,
            "file_size": adapter.file_size,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Failed to process completed OVISEN job {job_id}: {e}")
        return {"error": str(e)}
