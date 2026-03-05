"""Series Platform -- PARHEN Training Job Routes

Anti-sycophancy adapter training via MAPPO.
RunPod Serverless integration for GPU-accelerated training.

Endpoints:
  GET  /api/parhen/training/datasets     -> list anti-sycophancy datasets
  POST /api/parhen/training/launch       -> launch anti-sycophancy training
  GET  /api/parhen/training/jobs         -> list user's parhen jobs
  GET  /api/parhen/training/job/{id}     -> single job detail
  POST /api/parhen/training/callback     -> RunPod worker callback
  POST /api/parhen/training/cancel/{id}  -> cancel & refund
  POST /api/parhen/training/poll         -> admin: poll all active jobs
  GET  /api/parhen/training/dashboard/{key} -> public dashboard (no auth)
"""
import logging
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, ParhenTrainingJob, ParhenAdapter, Transaction
from .auth import get_current_user
from .config import (
    PARHEN_MODEL_COSTS, PARHEN_DATASETS, TIERS,
    PARHEN_INFERENCE_COSTS, RUNPOD_WEBHOOK_TOKEN,
    MODEL_HF_MAP, PARHEN_DATASET_MAP,
)
from .runpod_parhen_client import dispatch_parhen_job, check_parhen_status, cancel_parhen_job, process_completed_parhen_job

logger = logging.getLogger("parhen.training")

router = APIRouter(prefix="/api/parhen/training", tags=["parhen-training"])


class ParhenLaunchRequest(BaseModel):
    model: str
    dataset: str
    episodes: int


@router.get("/datasets")
async def list_parhen_datasets():
    """List available datasets for PARHEN anti-sycophancy training."""
    return [
        {
            "id": d["id"],
            "name": d["label"],
            "description": f"{d['tasks']} tasks, {d['categories']} categories",
            "size": f"{d['tasks']} tasks",
        }
        for d in PARHEN_DATASETS
    ]


@router.post("/launch")
async def launch_parhen_training(
    req: ParhenLaunchRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Launch PARHEN anti-sycophancy training -> RunPod GPU."""
    tier_info = TIERS.get(user.tier, TIERS["free"])

    model_info = PARHEN_MODEL_COSTS.get(req.model)
    if not model_info:
        raise HTTPException(400, f"Unknown model: {req.model}")

    dataset = next((d for d in PARHEN_DATASETS if d["id"] == req.dataset), None)
    if not dataset:
        raise HTTPException(400, f"Unknown dataset: {req.dataset}")

    max_ep = tier_info.get("max_episodes", 500)
    if req.episodes > max_ep:
        raise HTTPException(403, f"Max {max_ep} episodes on {tier_info['label']} tier")

    credits_needed = req.episodes * model_info["credits_per_episode"]
    if user.credits < credits_needed:
        raise HTTPException(402, f"Not enough credits. Need {credits_needed}, have {user.credits}.")

    user.credits -= credits_needed

    txn = Transaction(
        user_id=user.id,
        type="training",
        credits=-credits_needed,
        description=f"PARHEN Training: {model_info['label']} x {req.episodes} eps on {dataset['label']}",
    )
    db.add(txn)

    dash_key = secrets.token_hex(6).upper()
    job = ParhenTrainingJob(
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

    import os
    base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if base_url:
        callback_url = f"https://{base_url}/api/parhen/training/callback"
    else:
        callback_url = str(request.base_url).rstrip("/") + "/api/parhen/training/callback"

    runpod_result = dispatch_parhen_job(
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
        logger.error(f"RunPod PARHEN dispatch failed for job {job.id}: {runpod_result['error']}")
        db.commit()
        return {
            "job_id": job.id,
            "status": "queued",
            "model": model_info["label"],
            "dataset": dataset["label"],
            "episodes": req.episodes,
            "credits_used": credits_needed,
            "remaining_credits": user.credits,
            "message": f"PARHEN training queued! GPU dispatch pending -- {runpod_result['error']}",
            "dashboard_key": dash_key,
            "dashboard_url": f"/monitor?key={dash_key}&product=parhen",
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
        "message": f"PARHEN training dispatched to GPU! {credits_needed} credits deducted.",
        "dashboard_key": dash_key,
        "dashboard_url": f"/monitor?key={dash_key}&product=parhen",
    }


@router.get("/jobs")
async def list_parhen_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's PARHEN training jobs."""
    jobs = (
        db.query(ParhenTrainingJob)
        .filter(ParhenTrainingJob.user_id == user.id)
        .order_by(ParhenTrainingJob.created_at.desc())
        .limit(20)
        .all()
    )

    model_labels = {k: v["label"] for k, v in PARHEN_MODEL_COSTS.items()}
    dataset_labels = {d["id"]: d["label"] for d in PARHEN_DATASETS}

    for j in jobs:
        if j.runpod_request_id and j.status in ("dispatched", "running"):
            try:
                rp = check_parhen_status(j.runpod_request_id)
                _sync_parhen_from_runpod(j, rp, db)
            except Exception as e:
                logger.warning(f"Failed to sync PARHEN job {j.id}: {e}")
    db.commit()

    result = []
    for j in jobs:
        adapter = db.query(ParhenAdapter).filter(ParhenAdapter.training_job_id == j.id).first()
        adapter_info = None
        if adapter:
            inf_cost = PARHEN_INFERENCE_COSTS.get(j.model, {}).get("credits_per_call", 2)
            adapter_info = {
                "id": adapter.id,
                "name": adapter.name,
                "status": adapter.status,
                "file_size": adapter.file_size,
                "format": ".prh",
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
            "conviction": j.conviction,
            "independence": j.independence,
            "credits_used": j.credits_used,
            "adapter": adapter_info,
            "dashboard_key": j.dashboard_key,
            "dashboard_url": f"/monitor?key={j.dashboard_key}&product=parhen" if j.dashboard_key else None,
            "runpod_error": j.runpod_error,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        })

    return result


@router.get("/job/{job_id}")
async def get_parhen_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get single PARHEN job details."""
    job = db.query(ParhenTrainingJob).filter(
        ParhenTrainingJob.id == job_id,
        ParhenTrainingJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(404, "PARHEN job not found")

    if job.runpod_request_id and job.status in ("dispatched", "running"):
        try:
            rp = check_parhen_status(job.runpod_request_id)
            _sync_parhen_from_runpod(job, rp, db)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to sync PARHEN job {job.id}: {e}")

    model_info = PARHEN_MODEL_COSTS.get(job.model, {})
    progress = (job.current_episode / job.episodes * 100) if job.episodes > 0 else 0

    adapter = db.query(ParhenAdapter).filter(ParhenAdapter.training_job_id == job.id).first()
    adapter_info = None
    if adapter:
        inf_cost = PARHEN_INFERENCE_COSTS.get(job.model, {}).get("credits_per_call", 2)
        adapter_info = {
            "id": adapter.id,
            "name": adapter.name,
            "status": adapter.status,
            "file_size": adapter.file_size,
            "format": ".prh",
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
        "conviction": job.conviction,
        "independence": job.independence,
        "credits_used": job.credits_used,
        "adapter": adapter_info,
        "dashboard_key": job.dashboard_key,
        "dashboard_url": f"/monitor?key={job.dashboard_key}&product=parhen" if job.dashboard_key else None,
        "runpod_error": job.runpod_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/callback")
async def parhen_callback(request: Request, db: Session = Depends(get_db)):
    """RunPod PARHEN worker callback when training completes/fails."""
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

    job = db.query(ParhenTrainingJob).filter(ParhenTrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(404, f"PARHEN Job {job_id} not found")

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
                description=f"Refund: PARHEN job #{job.id} failed",
            ))
        db.commit()
        return {"status": "ok", "job_status": "failed"}

    if status == "completed":
        output = body.get("output", {})
        result = process_completed_parhen_job(
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
        job.conviction = body.get("conviction", job.conviction)
        job.independence = body.get("independence", job.independence)
        job.status = "running"
        if not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "ok"}

    return {"status": "ignored"}


@router.post("/cancel/{job_id}")
async def cancel_parhen(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel PARHEN training and refund credits."""
    job = db.query(ParhenTrainingJob).filter(
        ParhenTrainingJob.id == job_id,
        ParhenTrainingJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(404, "PARHEN job not found")
    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(400, f"Job already {job.status}")

    if job.runpod_request_id:
        try:
            cancel_parhen_job(job.runpod_request_id)
        except Exception as e:
            logger.warning(f"Failed to cancel PARHEN RunPod job: {e}")

    user.credits += job.credits_used
    db.add(Transaction(
        user_id=user.id, type="refund", credits=job.credits_used,
        description=f"Refund: PARHEN job #{job.id} cancelled",
    ))
    job.status = "cancelled"
    job.current_phase = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {"job_id": job.id, "status": "cancelled", "credits_refunded": job.credits_used, "new_balance": user.credits}


@router.post("/poll")
async def poll_parhen_jobs(db: Session = Depends(get_db)):
    """Admin: poll all active PARHEN jobs."""
    active = (
        db.query(ParhenTrainingJob)
        .filter(ParhenTrainingJob.status.in_(["dispatched", "running"]))
        .filter(ParhenTrainingJob.runpod_request_id.isnot(None))
        .all()
    )
    results = []
    for job in active:
        try:
            rp = check_parhen_status(job.runpod_request_id)
            changed = _sync_parhen_from_runpod(job, rp, db)
            results.append({"job_id": job.id, "status": job.status, "changed": changed})
        except Exception as e:
            results.append({"job_id": job.id, "error": str(e)})
    db.commit()
    return {"polled": len(active), "results": results}


# -- Public Dashboard --
_PHASE_MAP = {
    "queued": 0, "in_queue": 0, "dispatch_failed": 0,
    "warmup": 0, "initializing": 0,
    "baseline_calibration": 1, "pressure_testing": 1,
    "adversarial_pressure": 2, "conviction_training": 2, "training": 2,
    "independence_tuning": 3, "evaluation": 3,
    "distillation": 4, "export": 4,
    "completed": 4, "done": 4,
    "failed": -1, "cancelled": -1,
}
_PHASE_NAMES = {0: "Warmup", 1: "Baseline Calibration", 2: "Conviction Training", 3: "Independence Tuning", 4: "Distillation"}


@router.get("/dashboard/{key}")
async def get_parhen_dashboard(key: str, db: Session = Depends(get_db)):
    """Public PARHEN dashboard -- no auth required."""
    job = db.query(ParhenTrainingJob).filter(ParhenTrainingJob.dashboard_key == key.upper()).first()
    if not job:
        raise HTTPException(404, "Invalid dashboard key.")

    if job.runpod_request_id and job.status in ("dispatched", "running"):
        try:
            rp = check_parhen_status(job.runpod_request_id)
            _sync_parhen_from_runpod(job, rp, db)
            db.commit()
        except Exception:
            pass

    progress = (job.current_episode / job.episodes * 100) if job.episodes > 0 else 0
    phase_idx = _PHASE_MAP.get(job.current_phase, 0)
    phase_name = _PHASE_NAMES.get(phase_idx, job.current_phase)

    t = min(progress / 100, 1.0)
    conviction = t * 0.90
    independence = t * 0.85

    if job.conviction and job.conviction > 0:
        conviction = job.conviction
    if job.independence and job.independence > 0:
        independence = job.independence

    adapter = db.query(ParhenAdapter).filter(ParhenAdapter.training_job_id == job.id).first()
    adapter_info = None
    if adapter:
        adapter_info = {
            "id": adapter.id, "name": adapter.name,
            "status": adapter.status, "file_size": adapter.file_size, "format": ".prh",
        }

    model_info = PARHEN_MODEL_COSTS.get(job.model, {})
    dataset_labels = {d["id"]: d["label"] for d in PARHEN_DATASETS}

    status_map = {
        "queued": "initializing", "dispatched": "initializing",
        "running": "training", "completed": "completed",
        "failed": "failed", "cancelled": "cancelled",
    }

    return {
        "product": "parhen",
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
        "conviction": round(conviction, 4),
        "independence": round(independence, 4),
        "adapter": adapter_info,
        "error": job.runpod_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _sync_parhen_from_runpod(job: ParhenTrainingJob, rp_data: dict, db: Session) -> bool:
    """Sync PARHEN job status from RunPod API response."""
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
            result = process_completed_parhen_job(
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
                description=f"Refund: PARHEN job #{job.id} failed on GPU",
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
                description=f"Refund: PARHEN job #{job.id} {rp_status.lower()}",
            ))

    return job.status != old_status
