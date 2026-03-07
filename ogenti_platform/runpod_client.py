"""Ogenti Platform — RunPod Serverless Client

Handles:
  - Dispatching training jobs to RunPod Serverless endpoints
  - Polling job status
  - Cancelling jobs
  - Processing completed jobs (download adapter → encrypt → store .ogt)
"""

import httpx
import logging
import base64
from datetime import datetime, timezone

from .config import (
    RUNPOD_API_KEY,
    RUNPOD_ENDPOINT_ID,
    RUNPOD_API_BASE,
    RUNPOD_WEBHOOK_TOKEN,
    MODEL_HF_MAP,
    DATASET_HF_MAP,
    MODEL_COSTS,
)

logger = logging.getLogger("ogenti.runpod")


def _headers() -> dict:
    """RunPod API authentication headers."""
    key = RUNPOD_API_KEY
    if not key:
        import os
        key = os.getenv("RUNPOD_API_KEY", "")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _endpoint_url(path: str = "") -> str:
    """Build RunPod endpoint URL."""
    eid = RUNPOD_ENDPOINT_ID
    if not eid:
        import os
        eid = os.getenv("RUNPOD_ENDPOINT_ID", "")
    return f"{RUNPOD_API_BASE}/{eid}{path}"


def dispatch_training_job(
    job_id: int,
    model: str,
    dataset: str,
    episodes: int,
    user_id: int,
    callback_url: str = "",
    vision_model: str = None,
    products: list[str] = None,
    training_mode: str = "v1",
    dataset_tier: str = None,
) -> dict:
    """
    Dispatch a training job to RunPod Serverless.

    Args:
        products: List of products to train (e.g. ["ogenti", "ovisen", "murhen"])
        training_mode: "v1" (token protocol / LoRA) or "v2" (telepathy / SES)
        dataset_tier: "starter"|"basic"|"advanced"|"premium"|"ultimate"

    Returns:
        {"id": "runpod-request-id", "status": "IN_QUEUE"} on success
        {"error": "..."} on failure
    """
    import os
    api_key = os.getenv("RUNPOD_API_KEY", "") or RUNPOD_API_KEY
    endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "") or RUNPOD_ENDPOINT_ID

    if not api_key:
        return {"error": "RUNPOD_API_KEY not configured"}
    if not endpoint_id:
        return {"error": "RUNPOD_ENDPOINT_ID not configured"}

    # Map model to HuggingFace repo
    hf_model = MODEL_HF_MAP.get(model, model)
    dataset_info = DATASET_HF_MAP.get(dataset, {"type": "local", "path": dataset})

    # Build the training payload
    products_list = products or ["ogenti"]

    payload = {
        "input": {
            "job_id": job_id,
            "user_id": user_id,
            "model_id": hf_model,
            "model_key": model,
            "dataset": dataset_info,
            "dataset_id": dataset,
            "dataset_tier": dataset_tier or "starter",
            "episodes": episodes,
            "products": products_list,
            "training_mode": training_mode,
            "callback_url": callback_url,
            "callback_token": os.getenv("RUNPOD_WEBHOOK_TOKEN", RUNPOD_WEBHOOK_TOKEN),
        }
    }

    # v1: LoRA config (autoregressive token protocol)
    if training_mode == "v1":
        payload["input"].update({
            "lora_r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            "learning_rate": 2e-4,
            "batch_size": 4,
            "gradient_accumulation_steps": 4,
            "warmup_ratio": 0.03,
            "max_seq_length": 2048,
        })
    else:
        # v2: Telepathy SES config (projector-based, ~5MB output)
        payload["input"].update({
            "ses_dim": 512,
            "n_virtual_tokens": 4,
            "contrastive_tau": 0.07,
            "learning_rate": 3e-4,
            "batch_size": 32,
            "phases": [
                {"id": 0, "name": "SES Alignment",      "episodes_pct": 0.087},
                {"id": 1, "name": "Simple 1:1 Telepathy","episodes_pct": 0.217},
                {"id": 2, "name": "Multi-Agent Relay",   "episodes_pct": 0.348},
                {"id": 3, "name": "Cross-Model Transfer","episodes_pct": 0.217},
                {"id": 4, "name": "Emergent Composition", "episodes_pct": 0.130},
            ],
        })

    # Add vision model info if OVISEN training
    if vision_model:
        from .config import OVISEN_MODEL_HF_MAP
        payload["input"]["vision_model_key"] = vision_model
        payload["input"]["vision_model_id"] = OVISEN_MODEL_HF_MAP.get(vision_model, vision_model)

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/run"
        resp = httpx.post(url, json=payload, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"RunPod job dispatched: job_id={job_id}, runpod_id={data.get('id')}")
        return data
    except httpx.HTTPStatusError as e:
        error_msg = f"RunPod API error: {e.response.status_code} — {e.response.text}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"RunPod dispatch failed: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}


def check_job_status(runpod_request_id: str) -> dict:
    """
    Check RunPod job status.

    Returns dict with keys:
        - status: "IN_QUEUE" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "CANCELLED" | "TIMED_OUT"
        - output: {...} when COMPLETED
        - error: "..." when FAILED
    """
    import os
    endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "") or RUNPOD_ENDPOINT_ID

    if not endpoint_id:
        return {"status": "FAILED", "error": "RUNPOD_ENDPOINT_ID not configured"}

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/status/{runpod_request_id}"
        resp = httpx.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"RunPod status check failed: {e}")
        return {"status": "UNKNOWN", "error": str(e)}


def cancel_job(runpod_request_id: str) -> dict:
    """Cancel a RunPod job."""
    import os
    endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID", "") or RUNPOD_ENDPOINT_ID

    try:
        url = f"{RUNPOD_API_BASE}/{endpoint_id}/cancel/{runpod_request_id}"
        resp = httpx.post(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"RunPod cancel failed: {e}")
        return {"error": str(e)}


def process_completed_job(
    runpod_output: dict,
    job_id: int,
    user_id: int,
    model: str,
    db_session,
) -> dict:
    """
    Process RunPod job output:
      1. Decode base64 adapter weights
      2. Encrypt to product-specific format (.ogt/.oge/.phr/.prh/.mrh/.syh/.ser)
      3. Create Adapter record
      4. Update TrainingJob status

    The adapter extension is determined by the products list:
      - Single product: product-specific extension (.ogt, .oge, etc.)
      - Multiple products (combo): .ser (SER1ES unified)

    Returns:
        {"adapter_id": "...", "status": "completed"} or {"error": "..."}
    """
    from .database import TrainingJob, Adapter
    from .adapter import encrypt_and_store_adapter
    from .config import get_adapter_extension, PRODUCT_EXTENSIONS
    import json

    try:
        # Get the adapter weights
        adapter_b64 = runpod_output.get("adapter_base64", "")
        if not adapter_b64:
            return {"error": "No adapter weights in RunPod output"}

        safetensors_data = base64.b64decode(adapter_b64)
        if len(safetensors_data) == 0:
            return {"error": "Empty adapter weights"}

        # Get the training job
        job = db_session.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job:
            return {"error": f"TrainingJob {job_id} not found"}

        # Parse products from job
        products = json.loads(job.products) if job.products else ["ogenti"]
        training_mode = runpod_output.get("training_mode", "v1")
        adapter_ext = get_adapter_extension(products)

        # Get metrics
        metrics = runpod_output.get("metrics", {})
        accuracy = metrics.get("accuracy", 0.0)
        compression = metrics.get("compression", 0.0)
        # v2 metrics
        fidelity = metrics.get("fidelity", accuracy)
        effective_dim = metrics.get("effective_dim", 0.0)

        # Generate adapter name with product info
        model_label = MODEL_COSTS.get(model, {}).get("label", model)
        product_labels = [p.upper() for p in products]
        version_tag = "Telepathy" if training_mode == "v2" else "Protocol"
        if len(products) == 1:
            adapter_name = f"{product_labels[0]} {version_tag} Adapter #{job_id}"
        else:
            adapter_name = f"SER1ES Combo ({'+'.join(product_labels)}) {version_tag} #{job_id}"

        # Encrypt and store with correct extension
        adapter = encrypt_and_store_adapter(
            safetensors_data=safetensors_data,
            user_id=user_id,
            job=job,
            adapter_name=adapter_name,
            db=db_session,
            adapter_ext=adapter_ext,
            products=products,
            training_mode=training_mode,
        )

        # Update job
        job.status = "completed"
        job.current_phase = "completed"
        job.current_episode = job.episodes
        job.accuracy = fidelity if training_mode == "v2" else accuracy
        job.compression = compression
        job.completed_at = datetime.now(timezone.utc)

        db_session.commit()

        logger.info(
            f"Job {job_id} completed: adapter={adapter.id}, "
            f"products={products}, mode={training_mode}, "
            f"ext={adapter_ext}, size={adapter.file_size}"
        )
        return {
            "adapter_id": adapter.id,
            "adapter_name": adapter.name,
            "file_size": adapter.file_size,
            "format": adapter_ext,
            "products": products,
            "training_mode": training_mode,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Failed to process completed job {job_id}: {e}")
        return {"error": str(e)}
