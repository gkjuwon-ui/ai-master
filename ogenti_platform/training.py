"""Ogenti Platform — Training Job Routes

RunPod Serverless integration:
  - POST /launch     → creates job, dispatches to RunPod
  - GET  /jobs       → list jobs with RunPod status sync
  - GET  /job/{id}   → single job detail (polls RunPod if running)
  - POST /callback   → RunPod worker calls back with results
  - POST /cancel     → cancel a running job
  - POST /poll       → admin: manually poll all active jobs
  - GET  /dashboard/{key} → public dashboard data (no auth)
"""
import logging
import secrets
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session

from .database import get_db, User, TrainingJob, Transaction, Adapter
from .auth import get_current_user
from .config import MODEL_COSTS, DATASETS, TIERS, INFERENCE_COSTS, RUNPOD_WEBHOOK_TOKEN, PRODUCT_DATASETS, DATASET_TIERS, CUSTOM_DATASET_MAX_SIZE_MB, CUSTOM_DATASET_ALLOWED_EXTENSIONS, OVISEN_MODEL_COSTS
from .runpod_client import dispatch_training_job, check_job_status, cancel_job, process_completed_job

import json
logger = logging.getLogger("ogenti.training")

router = APIRouter(prefix="/api/training", tags=["training"])


class LaunchRequest(BaseModel):
    model: str
    vision_model: Optional[str] = None   # Vision model for OVISEN
    dataset: str = "ogenti-default"
    dataset_tier: Optional[str] = None   # "starter" | "basic" | "advanced" | "premium" | "ultimate"
    custom_dataset_id: Optional[str] = None  # ID from upload
    products: Optional[List[str]] = None
    episodes: int


@router.get("/datasets")
async def list_datasets():
    """List available datasets (legacy)"""
    result = []
    for d in DATASETS:
        result.append({"id": d["id"], "name": d["label"], "description": f"{d['tasks']} tasks, {d['categories']} categories", "size": f"{d['tasks']} tasks"})
    return result


@router.post("/upload-dataset")
async def upload_dataset(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Upload a custom dataset. Accepts .json, .jsonl, .txt, .md, .csv — we process internally."""
    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in CUSTOM_DATASET_ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}. Allowed: {', '.join(CUSTOM_DATASET_ALLOWED_EXTENSIONS)}")

    # Read + size check
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > CUSTOM_DATASET_MAX_SIZE_MB:
        raise HTTPException(400, f"File too large: {size_mb:.1f}MB. Max: {CUSTOM_DATASET_MAX_SIZE_MB}MB")

    # Validate it's valid text
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be valid UTF-8 text")

    # Count tasks (lines for jsonl/txt/csv, entries for json)
    task_count = 0
    if ext == ".json":
        import json as json_mod
        try:
            data = json_mod.loads(text)
            task_count = len(data) if isinstance(data, list) else 1
        except json_mod.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON format")
    elif ext == ".jsonl":
        task_count = sum(1 for line in text.strip().split("\n") if line.strip())
    else:
        # txt, md, csv — count non-empty lines
        task_count = sum(1 for line in text.strip().split("\n") if line.strip())

    # Store file
    upload_dir = os.getenv("CUSTOM_DATASET_DIR", "./custom_datasets")
    os.makedirs(upload_dir, exist_ok=True)
    dataset_id = f"custom-{uuid.uuid4().hex[:12]}"
    save_path = os.path.join(upload_dir, f"{dataset_id}{ext}")
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(text)

    return {
        "dataset_id": dataset_id,
        "filename": file.filename,
        "size_mb": round(size_mb, 2),
        "tasks": task_count,
        "format": ext,
        "message": f"Dataset uploaded! {task_count} entries detected. We'll process it automatically during training.",
    }


@router.post("/launch")
async def launch_training(req: LaunchRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Launch a training job → dispatches to RunPod Serverless GPU."""
    tier_info = TIERS.get(user.tier, TIERS["free"])

    # Validate model
    model_info = MODEL_COSTS.get(req.model)
    if not model_info:
        raise HTTPException(400, f"Unknown model: {req.model}")

    # Check model access
    allowed_models = tier_info["models"]
    if allowed_models != "all" and req.model not in allowed_models:
        raise HTTPException(403, f"Model {req.model} not available on {tier_info['label']} tier. Upgrade to access.")

    # Validate vision model if OVISEN selected
    vision_model_info = None
    vision_compute = 0
    products_list = req.products or ["ogenti"]
    has_ovisen = "ovisen" in products_list

    if has_ovisen:
        if not req.vision_model:
            raise HTTPException(400, "OVISEN requires a vision_model selection")
        vision_model_info = OVISEN_MODEL_COSTS.get(req.vision_model)
        if not vision_model_info:
            raise HTTPException(400, f"Unknown vision model: {req.vision_model}")
        vision_compute = req.episodes * vision_model_info["credits_per_episode"]

    # Validate dataset — support tiered product datasets, custom, and legacy
    dataset_credits = 0
    dataset_label = "Custom"

    # ── Log incoming request for debugging ──
    logger.info(f"LAUNCH v0.5.1 | user={user.id} model={req.model} dataset={req.dataset} dataset_tier={req.dataset_tier} products={products_list} episodes={req.episodes}")

    # Auto-detect dataset_tier from dataset field if not explicitly set
    # Handles: "starter-tier" → "starter", "ultimate-tier" → "ultimate", etc.
    if not req.dataset_tier and req.dataset:
        if req.dataset.endswith('-tier'):
            req.dataset_tier = req.dataset.replace('-tier', '')
            logger.info(f"Auto-detected dataset_tier='{req.dataset_tier}' from dataset='{req.dataset}'")
        elif req.dataset in DATASET_TIERS:
            # Frontend sent just the tier name (e.g. "ultimate") as dataset
            req.dataset_tier = req.dataset
            logger.info(f"Auto-detected dataset_tier='{req.dataset_tier}' (direct match)")

    if req.custom_dataset_id:
        # Custom uploaded dataset — no extra credits
        dataset_label = f"Custom Upload ({req.custom_dataset_id})"
        req.dataset = req.custom_dataset_id
    elif req.dataset_tier and req.dataset_tier in DATASET_TIERS:
        # Tiered product dataset — sum credits across all selected products
        for prod in products_list:
            prod_ds = PRODUCT_DATASETS.get(prod, {}).get(req.dataset_tier)
            if prod_ds:
                dataset_credits += prod_ds["credits"]
        tier_labels = [PRODUCT_DATASETS.get(p, {}).get(req.dataset_tier, {}).get("label", "?") for p in products_list]
        dataset_label = f"{req.dataset_tier.upper()} — {' + '.join(tier_labels)}"
        req.dataset = f"{req.dataset_tier}-tier"
    elif req.dataset_tier:
        # dataset_tier given but not in DATASET_TIERS — treat as starter
        logger.warning(f"Unknown dataset_tier '{req.dataset_tier}', falling back to starter")
        req.dataset_tier = "starter"
        for prod in products_list:
            prod_ds = PRODUCT_DATASETS.get(prod, {}).get("starter")
            if prod_ds:
                dataset_credits += prod_ds["credits"]
        dataset_label = "STARTER (FALLBACK)"
        req.dataset = "starter-tier"
    else:
        # Legacy dataset OR no dataset info — accept gracefully (NEVER raise 400)
        dataset = next((d for d in DATASETS if d["id"] == req.dataset), None)
        if dataset:
            dataset_label = dataset["label"]
        else:
            logger.warning(f"Unknown dataset '{req.dataset}', using starter fallback")
            dataset_label = "STARTER (AUTO)"
            req.dataset = "starter-tier"

    # Check episode limit
    if req.episodes > tier_info["max_episodes"]:
        raise HTTPException(403, f"Max {tier_info['max_episodes']} episodes on {tier_info['label']} tier")

    # Calculate cost (training compute + vision compute + dataset access fee)
    compute_credits = req.episodes * model_info["credits_per_episode"]
    credits_needed = compute_credits + vision_compute + dataset_credits
    if user.credits < credits_needed:
        raise HTTPException(
            402,
            f"Not enough credits. Need {credits_needed} (compute: {compute_credits} + vision: {vision_compute} + dataset: {dataset_credits}), have {user.credits}. Buy more credits.",
        )

    # Deduct credits
    user.credits -= credits_needed

    # Record usage transaction
    vision_label = f" + {vision_model_info['label']}" if vision_model_info else ""
    txn = Transaction(
        user_id=user.id,
        type="training",
        credits=-credits_needed,
        description=f"Training: {model_info['label']}{vision_label} × {req.episodes} eps | Dataset: {dataset_label}",
    )
    db.add(txn)

    # Create job
    dash_key = secrets.token_hex(6).upper()
    job = TrainingJob(
        user_id=user.id,
        model=req.model,
        dataset=req.dataset,
        products=json.dumps(products_list),
        episodes=req.episodes,
        credits_used=credits_needed,
        credits_estimated=credits_needed,
        status="queued",
        dashboard_key=dash_key,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # ── Dispatch to RunPod ──
    import os
    base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if base_url:
        callback_url = f"https://{base_url}/api/training/callback"
    else:
        # Fallback: construct from request
        callback_url = str(request.base_url).rstrip("/") + "/api/training/callback"

    runpod_result = dispatch_training_job(
        job_id=job.id,
        model=req.model,
        dataset=req.dataset,
        episodes=req.episodes,
        user_id=user.id,
        callback_url=callback_url,
        vision_model=req.vision_model,
    )

    if "error" in runpod_result:
        # RunPod dispatch failed — keep job as "queued", log error
        job.runpod_error = runpod_result["error"]
        job.current_phase = "dispatch_failed"
        logger.error(f"RunPod dispatch failed for job {job.id}: {runpod_result['error']}")
        db.commit()
        return {
            "job_id": job.id,
            "status": "queued",
            "model": model_info["label"],
            "dataset": dataset_label,
            "products": products_list,
            "episodes": req.episodes,
            "credits_used": credits_needed,
            "dataset_credits": dataset_credits,
            "remaining_credits": user.credits,
            "message": f"Training queued! Credits deducted. GPU dispatch pending — {runpod_result['error']}",
            "runpod_status": "dispatch_failed",
            "dashboard_key": dash_key,
            "dashboard_url": f"/monitor?key={dash_key}",
        }

    # RunPod accepted the job
    job.runpod_request_id = runpod_result.get("id", "")
    job.status = "dispatched"
    job.current_phase = "in_queue"
    db.commit()

    return {
        "job_id": job.id,
        "status": "dispatched",
        "model": model_info["label"],
        "dataset": dataset_label,
        "products": products_list,
        "episodes": req.episodes,
        "credits_used": credits_needed,
        "dataset_credits": dataset_credits,
        "remaining_credits": user.credits,
        "message": f"Training dispatched to GPU! {credits_needed} credits deducted.",
        "runpod_status": runpod_result.get("status", "IN_QUEUE"),
        "dashboard_key": dash_key,
        "dashboard_url": f"/monitor?key={dash_key}",
    }


@router.get("/jobs")
async def list_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List user's training jobs — syncs RunPod status for active jobs."""
    jobs = (
        db.query(TrainingJob)
        .filter(TrainingJob.user_id == user.id)
        .order_by(TrainingJob.created_at.desc())
        .limit(20)
        .all()
    )

    model_labels = {k: v["label"] for k, v in MODEL_COSTS.items()}
    dataset_labels = {d["id"]: d["label"] for d in DATASETS}

    # Sync status for active RunPod jobs
    for j in jobs:
        if j.runpod_request_id and j.status in ("dispatched", "running"):
            try:
                rp = check_job_status(j.runpod_request_id)
                _sync_job_from_runpod(j, rp, db)
            except Exception as e:
                logger.warning(f"Failed to sync RunPod status for job {j.id}: {e}")

    db.commit()

    result = []
    for j in jobs:
        # Check if adapter exists for this job
        adapter = db.query(Adapter).filter(Adapter.training_job_id == j.id).first()
        adapter_info = None
        if adapter:
            inf_cost = INFERENCE_COSTS.get(j.model, {}).get("credits_per_call", 1)
            adapter_info = {
                "id": adapter.id,
                "name": adapter.name,
                "status": adapter.status,
                "file_size": adapter.file_size,
                "format": ".ogt",
                "inference_count": adapter.inference_count,
                "credits_per_call": inf_cost,
            }

        result.append({
            "id": j.id,
            "status": j.status,
            "model": j.model,
            "model_label": model_labels.get(j.model, j.model),
            "dataset": j.dataset,
            "dataset_label": dataset_labels.get(j.dataset, j.dataset),
            "products": json.loads(j.products) if j.products else ["ogenti"],
            "episodes": j.episodes,
            "current_episode": j.current_episode,
            "current_phase": j.current_phase,
            "progress": (j.current_episode / j.episodes * 100) if j.episodes > 0 else 0,
            "accuracy": j.accuracy,
            "compression": j.compression,
            "credits_used": j.credits_used,
            "adapter_url": j.adapter_url,
            "adapter": adapter_info,
            "dashboard_key": j.dashboard_key,
            "dashboard_url": f"/monitor?key={j.dashboard_key}" if j.dashboard_key else None,
            "runpod_error": j.runpod_error,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        })

    return result


@router.get("/job/{job_id}")
@router.get("/jobs/{job_id}")
async def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get single job details — polls RunPod if active."""
    job = db.query(TrainingJob).filter(TrainingJob.id == job_id, TrainingJob.user_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    # Live sync with RunPod
    if job.runpod_request_id and job.status in ("dispatched", "running"):
        try:
            rp = check_job_status(job.runpod_request_id)
            _sync_job_from_runpod(job, rp, db)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to sync RunPod status for job {job.id}: {e}")

    model_info = MODEL_COSTS.get(job.model, {})
    progress = (job.current_episode / job.episodes * 100) if job.episodes > 0 else 0

    adapter = db.query(Adapter).filter(Adapter.training_job_id == job.id).first()
    adapter_info = None
    if adapter:
        inf_cost = INFERENCE_COSTS.get(job.model, {}).get("credits_per_call", 1)
        adapter_info = {
            "id": adapter.id,
            "name": adapter.name,
            "status": adapter.status,
            "file_size": adapter.file_size,
            "format": ".ogt",
            "inference_count": adapter.inference_count,
            "credits_per_call": inf_cost,
        }

    return {
        "id": job.id,
        "status": job.status,
        "model": job.model,
        "model_label": model_info.get("label", job.model),
        "dataset": job.dataset,
        "products": json.loads(job.products) if job.products else ["ogenti"],
        "episodes": job.episodes,
        "current_episode": job.current_episode,
        "current_phase": job.current_phase,
        "progress_pct": round(progress, 1),
        "accuracy": job.accuracy,
        "compression": job.compression,
        "credits_used": job.credits_used,
        "adapter_url": job.adapter_url,
        "adapter": adapter_info,
        "dashboard_key": job.dashboard_key,
        "dashboard_url": f"/monitor?key={job.dashboard_key}" if job.dashboard_key else None,
        "runpod_error": job.runpod_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/callback")
async def training_callback(request: Request, db: Session = Depends(get_db)):
    """
    RunPod worker calls this when training completes or fails.
    Receives adapter weights, encrypts to .ogt, creates Adapter record.
    """
    import os
    body = await request.json()

    # Verify callback token
    token = body.get("callback_token", "")
    expected_token = os.getenv("RUNPOD_WEBHOOK_TOKEN", RUNPOD_WEBHOOK_TOKEN)
    if token != expected_token:
        raise HTTPException(403, "Invalid callback token")

    job_id = body.get("job_id")
    status = body.get("status", "")  # "completed" or "failed"

    if not job_id:
        raise HTTPException(400, "Missing job_id")

    job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    if status == "failed":
        error_msg = body.get("error", "Unknown error from GPU worker")
        job.status = "failed"
        job.current_phase = "failed"
        job.runpod_error = error_msg
        job.completed_at = datetime.now(timezone.utc)

        # Refund credits on failure
        user = db.query(User).filter(User.id == job.user_id).first()
        if user:
            user.credits += job.credits_used
            refund_txn = Transaction(
                user_id=user.id,
                type="refund",
                credits=job.credits_used,
                description=f"Refund: Training job #{job.id} failed",
            )
            db.add(refund_txn)
            logger.info(f"Refunded {job.credits_used} credits to user {user.id} for failed job {job.id}")

        db.commit()
        return {"status": "ok", "job_status": "failed"}

    if status == "completed":
        output = body.get("output", {})
        result = process_completed_job(
            runpod_output=output,
            job_id=job_id,
            user_id=job.user_id,
            model=job.model,
            db_session=db,
        )

        if "error" in result:
            job.status = "failed"
            job.runpod_error = f"Post-processing failed: {result['error']}"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"status": "error", "detail": result["error"]}

        return {"status": "ok", "job_status": "completed", "adapter_id": result.get("adapter_id")}

    # Progress update
    if status == "progress":
        job.current_episode = body.get("current_episode", job.current_episode)
        job.current_phase = body.get("phase", job.current_phase)
        job.accuracy = body.get("accuracy", job.accuracy)
        job.status = "running"
        if not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "ok"}

    return {"status": "ignored", "detail": f"Unknown status: {status}"}


@router.post("/cancel/{job_id}")
async def cancel_training(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cancel a training job and refund remaining credits."""
    job = db.query(TrainingJob).filter(TrainingJob.id == job_id, TrainingJob.user_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(400, f"Job already {job.status}")

    # Cancel on RunPod
    if job.runpod_request_id:
        try:
            cancel_job(job.runpod_request_id)
        except Exception as e:
            logger.warning(f"Failed to cancel RunPod job {job.runpod_request_id}: {e}")

    # Refund credits
    user.credits += job.credits_used
    refund_txn = Transaction(
        user_id=user.id,
        type="refund",
        credits=job.credits_used,
        description=f"Refund: Training job #{job.id} cancelled",
    )
    db.add(refund_txn)

    job.status = "cancelled"
    job.current_phase = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "job_id": job.id,
        "status": "cancelled",
        "credits_refunded": job.credits_used,
        "new_balance": user.credits,
    }


@router.post("/poll")
async def poll_active_jobs(db: Session = Depends(get_db)):
    """
    Poll all active RunPod jobs and sync status.
    Can be called by a cron/scheduler or manually.
    """
    active_jobs = (
        db.query(TrainingJob)
        .filter(TrainingJob.status.in_(["dispatched", "running"]))
        .filter(TrainingJob.runpod_request_id.isnot(None))
        .all()
    )

    results = []
    for job in active_jobs:
        try:
            rp = check_job_status(job.runpod_request_id)
            changed = _sync_job_from_runpod(job, rp, db)
            results.append({"job_id": job.id, "status": job.status, "changed": changed})
        except Exception as e:
            results.append({"job_id": job.id, "error": str(e)})

    db.commit()
    return {"polled": len(active_jobs), "results": results}


# ── Public Dashboard API (no auth) ──

# Phase mapping: map current_phase string to numeric phase index
_PHASE_MAP = {
    "queued": 0, "in_queue": 0, "dispatch_failed": 0,
    "warmup": 0, "initializing": 0,
    "simple": 1, "basic_training": 1,
    "complex": 2, "training": 2, "fine_tuning": 2,
    "generalize": 3, "evaluation": 3,
    "universalize": 4, "export": 4,
    "completed": 4, "done": 4,
    "failed": -1, "cancelled": -1,
}

_PHASE_NAMES = {0: "Warmup", 1: "Simple", 2: "Complex", 3: "Generalize", 4: "Universalize"}


@router.get("/dashboard/{key}")
async def get_dashboard(key: str, db: Session = Depends(get_db)):
    """
    Public dashboard endpoint — no authentication required.
    Returns training job data formatted for the Protocol Monitor dashboard.
    """
    job = db.query(TrainingJob).filter(TrainingJob.dashboard_key == key.upper()).first()
    if not job:
        raise HTTPException(404, "Invalid dashboard key. Check your key and try again.")

    # Sync with RunPod if still active
    if job.runpod_request_id and job.status in ("dispatched", "running"):
        try:
            rp = check_job_status(job.runpod_request_id)
            _sync_job_from_runpod(job, rp, db)
            db.commit()
        except Exception as e:
            logger.warning(f"Dashboard: failed to sync job {job.id}: {e}")

    # Calculate derived metrics
    progress = (job.current_episode / job.episodes * 100) if job.episodes > 0 else 0
    phase_idx = _PHASE_MAP.get(job.current_phase, 0)
    phase_name = _PHASE_NAMES.get(phase_idx, job.current_phase)

    # Map training progress to dashboard metrics
    t = min(progress / 100, 1.0)  # normalized progress 0..1
    compression = max(1.0, 1.0 + t * 15.5)  # 1.0x → 16.5x
    fidelity = t * 0.98  # 0% → 98%
    avg_tokens = max(4, int(30 - t * 26))  # 30 → 4
    budget = max(4.0, 30 - t * 26)  # 30 → 4

    # If job already has real accuracy/compression from RunPod worker, use those
    if job.compression and job.compression > 0:
        compression = job.compression
    if job.accuracy and job.accuracy > 0:
        fidelity = job.accuracy

    # Adapter info
    adapter = db.query(Adapter).filter(Adapter.training_job_id == job.id).first()
    adapter_info = None
    if adapter:
        adapter_info = {
            "id": adapter.id,
            "name": adapter.name,
            "status": adapter.status,
            "file_size": adapter.file_size,
            "format": ".ogt",
        }

    model_info = MODEL_COSTS.get(job.model, {})
    dataset_labels = {d["id"]: d["label"] for d in DATASETS}

    # Status mapping for dashboard
    status_map = {
        "queued": "initializing",
        "dispatched": "initializing",
        "running": "training",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }

    return {
        "status": status_map.get(job.status, job.status),
        "job_status": job.status,
        "model": model_info.get("label", job.model),
        "model_id": job.model,
        "dataset": dataset_labels.get(job.dataset, job.dataset),
        "episodes": job.episodes,
        "current_episode": job.current_episode,
        "progress_pct": round(progress, 1),
        "phase": max(0, phase_idx),
        "phase_name": phase_name,
        "compression": round(compression, 1),
        "fidelity": round(fidelity, 4),
        "avg_tokens": avg_tokens,
        "budget": round(budget, 1),
        "adapter": adapter_info,
        "error": job.runpod_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/jobs/by-key/{key}")
async def get_job_by_key(key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Look up a training job by dashboard key."""
    job = db.query(TrainingJob).filter(
        TrainingJob.dashboard_key == key.upper(),
        TrainingJob.user_id == user.id
    ).first()
    if not job:
        raise HTTPException(404, "Job not found for this key")

    if job.runpod_request_id and job.status in ("dispatched", "running"):
        try:
            rp = check_job_status(job.runpod_request_id)
            _sync_job_from_runpod(job, rp, db)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to sync job {job.id}: {e}")

    model_info = MODEL_COSTS.get(job.model, {})
    progress = (job.current_episode / job.episodes * 100) if job.episodes > 0 else 0

    return {
        "id": job.id,
        "status": job.status,
        "model": job.model,
        "model_label": model_info.get("label", job.model),
        "dataset": job.dataset,
        "products": json.loads(job.products) if job.products else ["ogenti"],
        "episodes": job.episodes,
        "current_episode": job.current_episode,
        "current_phase": job.current_phase,
        "progress": round(progress, 1),
        "accuracy": job.accuracy,
        "compression": job.compression,
        "credits_used": job.credits_used,
        "dashboard_key": job.dashboard_key,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _sync_job_from_runpod(job: TrainingJob, rp_data: dict, db: Session) -> bool:
    """
    Sync a TrainingJob's status from RunPod API response.
    Returns True if status changed.
    """
    rp_status = rp_data.get("status", "")
    old_status = job.status

    if rp_status == "IN_QUEUE":
        job.status = "dispatched"
        job.current_phase = "in_queue"
    elif rp_status == "IN_PROGRESS":
        job.status = "running"
        job.current_phase = "training"
        if not job.started_at:
            job.started_at = datetime.now(timezone.utc)
    elif rp_status == "COMPLETED":
        # Process the output
        output = rp_data.get("output", {})
        if output and job.status != "completed":
            result = process_completed_job(
                runpod_output=output,
                job_id=job.id,
                user_id=job.user_id,
                model=job.model,
                db_session=db,
            )
            if "error" in result:
                job.status = "failed"
                job.runpod_error = f"Post-processing: {result['error']}"
            else:
                job.status = "completed"
                job.current_phase = "completed"
            job.completed_at = datetime.now(timezone.utc)
    elif rp_status == "FAILED":
        job.status = "failed"
        job.current_phase = "failed"
        job.runpod_error = rp_data.get("error", "RunPod execution failed")
        job.completed_at = datetime.now(timezone.utc)

        # Refund credits
        user = db.query(User).filter(User.id == job.user_id).first()
        if user:
            user.credits += job.credits_used
            refund_txn = Transaction(
                user_id=user.id,
                type="refund",
                credits=job.credits_used,
                description=f"Refund: Training job #{job.id} failed on GPU",
            )
            db.add(refund_txn)
    elif rp_status in ("CANCELLED", "TIMED_OUT"):
        job.status = "failed"
        job.current_phase = rp_status.lower()
        job.runpod_error = f"RunPod: {rp_status}"
        job.completed_at = datetime.now(timezone.utc)

        # Refund
        user = db.query(User).filter(User.id == job.user_id).first()
        if user:
            user.credits += job.credits_used
            refund_txn = Transaction(
                user_id=user.id,
                type="refund",
                credits=job.credits_used,
                description=f"Refund: Training job #{job.id} {rp_status.lower()}",
            )
            db.add(refund_txn)

    return job.status != old_status
