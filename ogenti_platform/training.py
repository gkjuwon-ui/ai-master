"""Ogenti Platform — Training Job Routes"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, TrainingJob, Transaction
from .auth import get_current_user
from .config import MODEL_COSTS, DATASETS, TIERS

router = APIRouter(prefix="/api/training", tags=["training"])


class LaunchRequest(BaseModel):
    model: str
    dataset: str
    episodes: int


@router.get("/datasets")
async def list_datasets():
    """List available datasets"""
    result = []
    for d in DATASETS:
        result.append({"id": d["id"], "name": d["label"], "description": f"{d['tasks']} tasks, {d['categories']} categories", "size": f"{d['tasks']} tasks"})
    return result


@router.post("/launch")
async def launch_training(req: LaunchRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Launch a training job (deducts credits)"""
    tier_info = TIERS.get(user.tier, TIERS["free"])

    # Validate model
    model_info = MODEL_COSTS.get(req.model)
    if not model_info:
        raise HTTPException(400, f"Unknown model: {req.model}")

    # Check model access
    allowed_models = tier_info["models"]
    if allowed_models != "all" and req.model not in allowed_models:
        raise HTTPException(403, f"Model {req.model} not available on {tier_info['label']} tier. Upgrade to access.")

    # Validate dataset
    dataset = next((d for d in DATASETS if d["id"] == req.dataset), None)
    if not dataset:
        raise HTTPException(400, f"Unknown dataset: {req.dataset}")

    # Check episode limit
    if req.episodes > tier_info["max_episodes"]:
        raise HTTPException(403, f"Max {tier_info['max_episodes']} episodes on {tier_info['label']} tier")

    # Calculate cost
    credits_needed = req.episodes * model_info["credits_per_episode"]
    if user.credits < credits_needed:
        raise HTTPException(
            402,
            f"Not enough credits. Need {credits_needed}, have {user.credits}. Buy more credits.",
        )

    # Deduct credits
    user.credits -= credits_needed

    # Record usage transaction
    txn = Transaction(
        user_id=user.id,
        type="training",
        credits=-credits_needed,
        description=f"Training: {model_info['label']} × {req.episodes} eps on {dataset['label']}",
    )
    db.add(txn)

    # Create job
    job = TrainingJob(
        user_id=user.id,
        model=req.model,
        dataset=req.dataset,
        episodes=req.episodes,
        credits_used=credits_needed,
        credits_estimated=credits_needed,
        status="queued",
    )
    db.add(job)
    db.commit()

    return {
        "job_id": job.id,
        "status": "queued",
        "model": model_info["label"],
        "dataset": dataset["label"],
        "episodes": req.episodes,
        "credits_used": credits_needed,
        "remaining_credits": user.credits,
        "message": f"Training queued! {credits_needed} credits deducted.",
    }


@router.get("/jobs")
async def list_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List user's training jobs"""
    jobs = (
        db.query(TrainingJob)
        .filter(TrainingJob.user_id == user.id)
        .order_by(TrainingJob.created_at.desc())
        .limit(20)
        .all()
    )

    model_labels = {k: v["label"] for k, v in MODEL_COSTS.items()}
    dataset_labels = {d["id"]: d["label"] for d in DATASETS}

    return [
        {
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
            "accuracy": j.accuracy,
            "compression": j.compression,
            "credits_used": j.credits_used,
            "adapter_url": j.adapter_url,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/job/{job_id}")
async def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get single job details"""
    job = db.query(TrainingJob).filter(TrainingJob.id == job_id, TrainingJob.user_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    model_info = MODEL_COSTS.get(job.model, {})
    progress = (job.current_episode / job.episodes * 100) if job.episodes > 0 else 0

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
        "accuracy": job.accuracy,
        "compression": job.compression,
        "credits_used": job.credits_used,
        "adapter_url": job.adapter_url,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
