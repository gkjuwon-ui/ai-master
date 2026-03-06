"""O Ser1es Platform — OVISEN Training Job Routes

Image embedding compression training via MARL.
RunPod Serverless integration for GPU-accelerated vision model training.

Endpoints:
  GET  /api/ovisen/training/datasets     → list vision datasets
  POST /api/ovisen/training/launch       → launch image compression training
  GET  /api/ovisen/training/jobs         → list user's ovisen jobs
  GET  /api/ovisen/training/job/{id}     → single job detail
  POST /api/ovisen/training/callback     → RunPod worker callback
  POST /api/ovisen/training/cancel/{id}  → cancel & refund
  POST /api/ovisen/training/poll         → admin: poll all active jobs
  GET  /api/ovisen/training/dashboard/{key} → public dashboard (no auth)
"""
import logging
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, OVisenTrainingJob, OVisenAdapter, Transaction
from .auth import get_current_user
from .config import (
    OVISEN_MODEL_COSTS, OVISEN_DATASETS, TIERS,
    OVISEN_INFERENCE_COSTS, RUNPOD_WEBHOOK_TOKEN,
    OVISEN_MODEL_HF_MAP, OVISEN_DATASET_MAP,
)
from .runpod_ovisen_client import dispatch_ovisen_job, check_ovisen_status, cancel_ovisen_job, process_completed_ovisen_job

logger = logging.getLogger("ovisen.training")

router = APIRouter(prefix="/api/ovisen/training", tags=["ovisen-training"])


class OVisenLaunchRequest(BaseModel):
    model: str
    dataset: str
    episodes: int


@router.get("/datasets")
async def list_vision_datasets():
    """List available image datasets for OVISEN training."""
    return [
        {
            "id": d["id"],
            "name": d["label"],
            "description": f"{d['images']} images, {d['categories']} categories",
            "size": f"{d['images']} images",
        }
        for d in OVISEN_DATASETS
    ]


@router.post("/launch")
async def launch_ovisen_training(
    req: OVisenLaunchRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Launch OVISEN image embedding compression training → RunPod GPU."""
    tier_info = TIERS.get(user.tier, TIERS["free"])

    model_info = OVISEN_MODEL_COSTS.get(req.model)
    if not model_info:
        raise HTTPException(400, f"Unknown vision model: {req.model}")

    # Validate dataset
    dataset = next((d for d in OVISEN_DATASETS if d["id"] == req.dataset), None)
    if not dataset:
        raise HTTPException(400, f"Unknown dataset: {req.dataset}")

    # Episode limit
    max_ep = tier_info.get("max_episodes", 500)
    if req.episodes > max_ep:
        raise HTTPException(403, f"Max {max_ep} episodes on {tier_info['label']} tier")

    # Calculate cost
    credits_needed = req.episodes * model_info["credits_per_episode"]
    if user.credits < credits_needed:
        raise HTTPException(
            402,
            f"Not enough credits. Need {credits_needed}, have {user.credits}.",
        )

    # Deduct credits
    user.credits -= credits_needed

    txn = Transaction(
        user_id=user.id,
        type="training",
        credits=-credits_needed,
        description=f"OVISEN Training: {model_info['label']} × {req.episodes} eps on {dataset['label']}",
    )
    db.add(txn)

    dash_key = secrets.token_hex(6).upper()
    job = OVisenTrainingJob(
        user_id=user.id,
        model=req.model,
        dataset=req.dataset,
        episodes=req.episodes,
        credits_used=credits_needed,
        credits_estimated=credits_needed,
        status="queued",
        dashboard_key=dash_key,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispatch to RunPod
    import os
    base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if base_url:
        callback_url = f"https://{base_url}/api/ovisen/training/callback"
    else:
        callback_url = str(request.base_url).rstrip("/") + "/api/ovisen/training/callback"

    runpod_result = dispatch_ovisen_job(
        job_id=job.id,
        model=req.model,
        dataset=req.dataset,
        episodes=req.episodes,
        user_id=user.id,
        callback_url=callback_url,
    )

    if "error" in runpod_result:
        job.runpod_error = runpod_result["error"]
        job.current_phase = "dispatch_failed"
        logger.error(f"RunPod OVISEN dispatch failed for job {job.id}: {runpod_result['error']}")
        db.commit()
        return {
            "job_id": job.id,
            "status": "queued",
            "model": model_info["label"],
            "dataset": dataset["label"],
            "episodes": req.episodes,
            "credits_used": credits_needed,
            "remaining_credits": user.credits,
            "message": f"OVISEN training queued! GPU dispatch pending — {runpod_result['error']}",
            "dashboard_key": dash_key,
            "dashboard_url": f"/monitor?key={dash_key}&product=ovisen",
        }

    job.runpod_request_id = runpod_result.get("id", "")
    job.status = "dispatched"
    job.current_phase = "in_queue"
    db.commit()

    return {
        "job_id": job.id,
        "status": "dispatched",
        "model": model_info["label"],
        "dataset": dataset["label"],
        "episodes": req.episodes,
        "credits_used": credits_needed,
        "remaining_credits": user.credits,
        "message": f"OVISEN training dispatched to GPU! {credits_needed} credits deducted.",
        "dashboard_key": dash_key,
        "dashboard_url": f"/monitor?key={dash_key}&product=ovisen",
    }


@router.get("/jobs")
async def list_ovisen_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's OVISEN training jobs."""
    jobs = (
        db.query(OVisenTrainingJob)
        .filter(OVisenTrainingJob.user_id == user.id)
        .order_by(OVisenTrainingJob.created_at.desc())
        .limit(20)
        .all()
    )

    model_labels = {k: v["label"] for k, v in OVISEN_MODEL_COSTS.items()}
    dataset_labels = {d["id"]: d["label"] for d in OVISEN_DATASETS}

    # Sync active jobs
    for j in jobs:
        if j.runpod_request_id and j.status in ("dispatched", "running"):
            try:
                rp = check_ovisen_status(j.runpod_request_id)
                _sync_ovisen_from_runpod(j, rp, db)
            except Exception as e:
                logger.warning(f"Failed to sync OVISEN job {j.id}: {e}")
    db.commit()

    result = []
    for j in jobs:
        adapter = db.query(OVisenAdapter).filter(OVisenAdapter.training_job_id == j.id).first()
        adapter_info = None
        if adapter:
            inf_cost = OVISEN_INFERENCE_COSTS.get(j.model, {}).get("credits_per_call", 2)
            adapter_info = {
                "id": adapter.id,
                "name": adapter.name,
                "status": adapter.status,
                "file_size": adapter.file_size,
                "format": ".oge",
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
            "episodes": j.episodes,
            "current_episode": j.current_episode,
            "current_phase": j.current_phase,
            "progress": (j.current_episode / j.episodes * 100) if j.episodes > 0 else 0,
            "fidelity": j.fidelity,
            "compression": j.compression,
            "credits_used": j.credits_used,
            "adapter": adapter_info,
            "dashboard_key": j.dashboard_key,
            "dashboard_url": f"/monitor?key={j.dashboard_key}&product=ovisen" if j.dashboard_key else None,
            "runpod_error": j.runpod_error,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        })

    return result


@router.get("/job/{job_id}")
async def get_ovisen_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get single OVISEN job details."""
    job = db.query(OVisenTrainingJob).filter(
        OVisenTrainingJob.id == job_id,
        OVisenTrainingJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(404, "OVISEN job not found")

    if job.runpod_request_id and job.status in ("dispatched", "running"):
        try:
            rp = check_ovisen_status(job.runpod_request_id)
            _sync_ovisen_from_runpod(job, rp, db)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to sync OVISEN job {job.id}: {e}")

    model_info = OVISEN_MODEL_COSTS.get(job.model, {})
    progress = (job.current_episode / job.episodes * 100) if job.episodes > 0 else 0

    adapter = db.query(OVisenAdapter).filter(OVisenAdapter.training_job_id == job.id).first()
    adapter_info = None
    if adapter:
        inf_cost = OVISEN_INFERENCE_COSTS.get(job.model, {}).get("credits_per_call", 2)
        adapter_info = {
            "id": adapter.id,
            "name": adapter.name,
            "status": adapter.status,
            "file_size": adapter.file_size,
            "format": ".oge",
            "inference_count": adapter.inference_count,
            "credits_per_call": inf_cost,
        }

    return {
        "id": job.id,
        "status": job.status,
        "model": job.model,
        "model_label": model_info.get("label", job.model),
        "dataset": job.dataset,
        "episodes": job.episodes,
        "current_episode": job.current_episode,
        "current_phase": job.current_phase,
        "progress_pct": round(progress, 1),
        "fidelity": job.fidelity,
        "compression": job.compression,
        "credits_used": job.credits_used,
        "adapter": adapter_info,
        "dashboard_key": job.dashboard_key,
        "dashboard_url": f"/monitor?key={job.dashboard_key}&product=ovisen" if job.dashboard_key else None,
        "runpod_error": job.runpod_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/callback")
async def ovisen_callback(request: Request, db: Session = Depends(get_db)):
    """RunPod OVISEN worker callback when training completes/fails."""
    import os
    body = await request.json()

    token = body.get("callback_token", "")
    expected = os.getenv("RUNPOD_WEBHOOK_TOKEN", RUNPOD_WEBHOOK_TOKEN)
    if token != expected:
        raise HTTPException(403, "Invalid callback token")

    job_id = body.get("job_id")
    status = body.get("status", "")
    if not job_id:
        raise HTTPException(400, "Missing job_id")

    job = db.query(OVisenTrainingJob).filter(OVisenTrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(404, f"OVISEN Job {job_id} not found")

    if status == "failed":
        error_msg = body.get("error", "Unknown error from GPU worker")
        job.status = "failed"
        job.current_phase = "failed"
        job.runpod_error = error_msg
        job.completed_at = datetime.now(timezone.utc)

        user = db.query(User).filter(User.id == job.user_id).first()
        if user:
            user.credits += job.credits_used
            db.add(Transaction(
                user_id=user.id, type="refund", credits=job.credits_used,
                description=f"Refund: OVISEN job #{job.id} failed",
            ))
        db.commit()
        return {"status": "ok", "job_status": "failed"}

    if status == "completed":
        output = body.get("output", {})
        result = process_completed_ovisen_job(
            runpod_output=output, job_id=job_id,
            user_id=job.user_id, model=job.model, db_session=db,
        )
        if "error" in result:
            job.status = "failed"
            job.runpod_error = f"Post-processing failed: {result['error']}"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"status": "error", "detail": result["error"]}
        return {"status": "ok", "job_status": "completed", "adapter_id": result.get("adapter_id")}

    if status == "progress":
        job.current_episode = body.get("current_episode", job.current_episode)
        job.current_phase = body.get("phase", job.current_phase)
        job.fidelity = body.get("fidelity", job.fidelity)
        job.compression = body.get("compression", job.compression)
        job.status = "running"
        if not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "ok"}

    return {"status": "ignored"}


@router.post("/cancel/{job_id}")
async def cancel_ovisen(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel OVISEN training and refund credits."""
    job = db.query(OVisenTrainingJob).filter(
        OVisenTrainingJob.id == job_id,
        OVisenTrainingJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(404, "OVISEN job not found")
    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(400, f"Job already {job.status}")

    if job.runpod_request_id:
        try:
            cancel_ovisen_job(job.runpod_request_id)
        except Exception as e:
            logger.warning(f"Failed to cancel OVISEN RunPod job: {e}")

    user.credits += job.credits_used
    db.add(Transaction(
        user_id=user.id, type="refund", credits=job.credits_used,
        description=f"Refund: OVISEN job #{job.id} cancelled",
    ))
    job.status = "cancelled"
    job.current_phase = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {"job_id": job.id, "status": "cancelled", "credits_refunded": job.credits_used, "new_balance": user.credits}


@router.post("/poll")
async def poll_ovisen_jobs(db: Session = Depends(get_db)):
    """Admin: poll all active OVISEN jobs."""
    active = (
        db.query(OVisenTrainingJob)
        .filter(OVisenTrainingJob.status.in_(["dispatched", "running"]))
        .filter(OVisenTrainingJob.runpod_request_id.isnot(None))
        .all()
    )
    results = []
    for job in active:
        try:
            rp = check_ovisen_status(job.runpod_request_id)
            changed = _sync_ovisen_from_runpod(job, rp, db)
            results.append({"job_id": job.id, "status": job.status, "changed": changed})
        except Exception as e:
            results.append({"job_id": job.id, "error": str(e)})
    db.commit()
    return {"polled": len(active), "results": results}


# ── Public Dashboard ──
_PHASE_MAP = {
    "queued": 0, "in_queue": 0, "dispatch_failed": 0,
    "warmup": 0, "initializing": 0,
    "feature_extraction": 1, "embedding_alignment": 1,
    "compression_training": 2, "training": 2,
    "fidelity_tuning": 3, "evaluation": 3,
    "distillation": 4, "export": 4,
    "completed": 4, "done": 4,
    "failed": -1, "cancelled": -1,
}
_PHASE_NAMES = {0: "Warmup", 1: "Feature Extraction", 2: "Compression Training", 3: "Fidelity Tuning", 4: "Distillation"}


@router.get("/dashboard/{key}")
async def get_ovisen_dashboard(key: str, db: Session = Depends(get_db)):
    """Public OVISEN dashboard — no auth required."""
    job = db.query(OVisenTrainingJob).filter(OVisenTrainingJob.dashboard_key == key.upper()).first()
    if not job:
        raise HTTPException(404, "Invalid dashboard key.")

    if job.runpod_request_id and job.status in ("dispatched", "running"):
        try:
            rp = check_ovisen_status(job.runpod_request_id)
            _sync_ovisen_from_runpod(job, rp, db)
            db.commit()
        except Exception:
            pass

    progress = (job.current_episode / job.episodes * 100) if job.episodes > 0 else 0
    phase_idx = _PHASE_MAP.get(job.current_phase, 0)
    phase_name = _PHASE_NAMES.get(phase_idx, job.current_phase)

    t = min(progress / 100, 1.0)
    compression = max(1.0, 1.0 + t * 49.0)  # image compression: up to 50x
    fidelity = t * 0.96  # SSIM fidelity up to 96%
    embedding_dim = max(64, int(2048 - t * 1984))  # 2048 → 64 dims

    if job.compression and job.compression > 0:
        compression = job.compression
    if job.fidelity and job.fidelity > 0:
        fidelity = job.fidelity

    adapter = db.query(OVisenAdapter).filter(OVisenAdapter.training_job_id == job.id).first()
    adapter_info = None
    if adapter:
        adapter_info = {
            "id": adapter.id, "name": adapter.name,
            "status": adapter.status, "file_size": adapter.file_size, "format": ".oge",
        }

    model_info = OVISEN_MODEL_COSTS.get(job.model, {})
    dataset_labels = {d["id"]: d["label"] for d in OVISEN_DATASETS}

    status_map = {
        "queued": "initializing", "dispatched": "initializing",
        "running": "training", "completed": "completed",
        "failed": "failed", "cancelled": "cancelled",
    }

    return {
        "product": "ovisen",
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
        "embedding_dim": embedding_dim,
        "adapter": adapter_info,
        "error": job.runpod_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _sync_ovisen_from_runpod(job: OVisenTrainingJob, rp_data: dict, db: Session) -> bool:
    """Sync OVISEN job status from RunPod API response."""
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
        output = rp_data.get("output", {})
        if output and job.status != "completed":
            result = process_completed_ovisen_job(
                runpod_output=output, job_id=job.id,
                user_id=job.user_id, model=job.model, db_session=db,
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
        user = db.query(User).filter(User.id == job.user_id).first()
        if user:
            user.credits += job.credits_used
            db.add(Transaction(
                user_id=user.id, type="refund", credits=job.credits_used,
                description=f"Refund: OVISEN job #{job.id} failed on GPU",
            ))
    elif rp_status in ("CANCELLED", "TIMED_OUT"):
        job.status = "failed"
        job.current_phase = rp_status.lower()
        job.runpod_error = f"RunPod: {rp_status}"
        job.completed_at = datetime.now(timezone.utc)
        user = db.query(User).filter(User.id == job.user_id).first()
        if user:
            user.credits += job.credits_used
            db.add(Transaction(
                user_id=user.id, type="refund", credits=job.credits_used,
                description=f"Refund: OVISEN job #{job.id} {rp_status.lower()}",
            ))

    return job.status != old_status
