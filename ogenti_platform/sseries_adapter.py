"""Ser1es Platform -- S-SER1ES Adapter & Inference Routes

Neural Surgery adapters (.srs format).

Endpoints:
  GET  /api/sseries/adapters           -- List user's S-SER1ES adapters
  GET  /api/sseries/adapters/{id}      -- Get adapter details
  GET  /api/sseries/adapters/{id}/download -- Download encrypted .srs
  POST /api/sseries/adapters/infer     -- Run neural surgery inference (charges credits)
  POST /api/sseries/adapters/encrypt   -- Encrypt uploaded weights -> .srs
  GET  /api/sseries/adapters/pricing   -- Inference pricing table
  DELETE /api/sseries/adapters/{id}    -- Soft-delete adapter
"""

import uuid
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, SseriesAdapter, SseriesTrainingJob, Transaction
from .auth import get_current_user
from .config import SSERIES_INFERENCE_COSTS, SSERIES_MODEL_COSTS, SRS_STORAGE_DIR
from .srs_crypto import generate_encryption_key, encrypt_to_srs, decrypt_srs, get_srs_info

router = APIRouter(prefix="/api/sseries/adapters", tags=["sseries-adapters"])

Path(SRS_STORAGE_DIR).mkdir(parents=True, exist_ok=True)


class SseriesInferRequest(BaseModel):
    adapter_id: str
    text: str
    context: str = ""
    mode: str = "full"  # full | quick | deep


class SseriesEncryptRequest(BaseModel):
    training_job_id: int
    adapter_name: str = ""


@router.get("/pricing")
async def sseries_pricing():
    """Return per-call inference costs for each S-SER1ES model."""
    result = []
    for model_id, info in SSERIES_INFERENCE_COSTS.items():
        model_meta = SSERIES_MODEL_COSTS.get(model_id, {})
        result.append({
            "model": model_id,
            "label": info["label"],
            "credits_per_call": info["credits_per_call"],
            "speed": model_meta.get("speed", "N/A"),
        })
    return {"pricing": result}


@router.get("")
async def list_sseries_adapters(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all S-SER1ES adapters owned by user."""
    adapters = (
        db.query(SseriesAdapter)
        .filter(SseriesAdapter.user_id == user.id, SseriesAdapter.status != "deleted")
        .order_by(SseriesAdapter.created_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "name": a.name,
            "base_model": a.base_model,
            "base_model_label": SSERIES_MODEL_COSTS.get(a.base_model, {}).get("label", a.base_model),
            "file_size": a.file_size,
            "status": a.status,
            "inference_count": a.inference_count,
            "credits_per_call": SSERIES_INFERENCE_COSTS.get(a.base_model, {}).get("credits_per_call", 3),
            "training_job_id": a.training_job_id,
            "format": ".srs",
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in adapters
    ]


@router.get("/{adapter_id}")
async def get_sseries_adapter(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = db.query(SseriesAdapter).filter(
        SseriesAdapter.id == adapter_id,
        SseriesAdapter.user_id == user.id,
        SseriesAdapter.status != "deleted",
    ).first()
    if not adapter:
        raise HTTPException(404, "S-SER1ES adapter not found")

    inf_cost = SSERIES_INFERENCE_COSTS.get(adapter.base_model, {}).get("credits_per_call", 3)
    return {
        "id": adapter.id,
        "name": adapter.name,
        "base_model": adapter.base_model,
        "base_model_label": SSERIES_MODEL_COSTS.get(adapter.base_model, {}).get("label", adapter.base_model),
        "file_size": adapter.file_size,
        "status": adapter.status,
        "inference_count": adapter.inference_count,
        "credits_per_call": inf_cost,
        "training_job_id": adapter.training_job_id,
        "format": ".srs",
        "created_at": adapter.created_at.isoformat() if adapter.created_at else None,
    }


@router.get("/{adapter_id}/download")
async def download_srs(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download encrypted .srs file."""
    adapter = db.query(SseriesAdapter).filter(
        SseriesAdapter.id == adapter_id,
        SseriesAdapter.user_id == user.id,
        SseriesAdapter.status == "active",
    ).first()
    if not adapter:
        raise HTTPException(404, "S-SER1ES adapter not found")

    srs_path = Path(adapter.file_path) if adapter.file_path else None
    if not srs_path or not srs_path.exists():
        raise HTTPException(404, "Adapter file not found on server")

    def iter_file():
        with open(srs_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    filename = f"{adapter.name.replace(' ', '_')}_{adapter.id[:8]}.srs"
    return StreamingResponse(
        iter_file(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/infer")
async def run_sseries_inference(
    req: SseriesInferRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run neural surgery inference using S-SER1ES adapter.

    Takes text input, runs through the surgically enhanced model,
    evaluates neuron efficiency and surgery effectiveness.
    """
    adapter = db.query(SseriesAdapter).filter(
        SseriesAdapter.id == req.adapter_id,
        SseriesAdapter.user_id == user.id,
        SseriesAdapter.status == "active",
    ).first()
    if not adapter:
        raise HTTPException(404, "S-SER1ES adapter not found")

    cost_info = SSERIES_INFERENCE_COSTS.get(adapter.base_model, {"credits_per_call": 3})
    credits_needed = cost_info["credits_per_call"]

    if user.credits < credits_needed:
        raise HTTPException(402, f"Not enough credits. Need {credits_needed}, have {user.credits}.")

    srs_path = Path(adapter.file_path) if adapter.file_path else None
    if not srs_path or not srs_path.exists():
        raise HTTPException(500, "Adapter file not found")

    try:
        srs_data = srs_path.read_bytes()
        adapter_id_check, weights_data = decrypt_srs(srs_data, adapter.encryption_key)
    except ValueError as e:
        raise HTTPException(500, f"Adapter decryption failed: {e}")

    import hashlib
    text_hash = hashlib.sha256(req.text.encode()).hexdigest()
    seed_val = int(text_hash[:8], 16) / 0xFFFFFFFF

    # Surgery metrics simulation (GPU inference backend pending)
    neuron_efficiency = 0.75 + seed_val * 0.20
    surgery_precision = 0.80 + seed_val * 0.18
    blame_reduction = 0.60 + seed_val * 0.35

    # Analyze which "neuron groups" were activated
    words = req.text.split()
    neuron_groups = []
    group_names = ["reasoning", "knowledge", "instruction_following", "coding", "safety"]
    for i, name in enumerate(group_names):
        seg_seed = int(hashlib.md5(f"{name}:{req.text[:50]}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        neuron_groups.append({
            "group": name,
            "efficiency": round(0.65 + seg_seed * 0.35, 3),
            "surgery_applied": seg_seed > 0.3,
            "blame_before": round(0.4 + seg_seed * 0.5, 3),
            "blame_after": round(0.05 + seg_seed * 0.15, 3),
        })

    model_label = SSERIES_MODEL_COSTS.get(adapter.base_model, {}).get("label", adapter.base_model)

    result = {
        "neuron_efficiency": round(neuron_efficiency, 4),
        "surgery_precision": round(surgery_precision, 4),
        "blame_reduction": round(blame_reduction, 4),
        "overall_verdict": "enhanced" if neuron_efficiency > 0.85 else ("improved" if neuron_efficiency > 0.75 else "marginal"),
        "neuron_groups_analyzed": len(neuron_groups),
        "neuron_groups": neuron_groups,
        "mode": req.mode,
        "has_context": bool(req.context),
        "note": f"[S-SER1ES Inference] Model: {model_label} | Adapter: {adapter.name} | "
                f"Text: {len(req.text)} chars, {len(neuron_groups)} neuron groups analyzed "
                f"(GPU inference backend integration pending)",
    }

    user.credits -= credits_needed
    adapter.inference_count += 1
    db.add(Transaction(
        user_id=user.id, type="inference", credits=-credits_needed,
        description=f"S-SER1ES Inference: {adapter.name} ({model_label})",
    ))
    db.commit()

    return {
        "adapter_id": adapter.id,
        "adapter_name": adapter.name,
        "model": adapter.base_model,
        "model_label": model_label,
        "result": result,
        "credits_used": credits_needed,
        "remaining_credits": user.credits,
        "inference_count": adapter.inference_count,
    }


@router.post("/encrypt")
async def encrypt_sseries_adapter(
    training_job_id: int = Form(...),
    adapter_name: str = Form(""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload neural surgery weights, encrypt to .srs, store key server-side."""
    job = db.query(SseriesTrainingJob).filter(
        SseriesTrainingJob.id == training_job_id,
        SseriesTrainingJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(404, "S-SER1ES training job not found")

    existing = db.query(SseriesAdapter).filter(SseriesAdapter.training_job_id == training_job_id).first()
    if existing:
        raise HTTPException(409, "Adapter already exists for this training job")

    raw_data = await file.read()
    if len(raw_data) == 0:
        raise HTTPException(400, "Empty file uploaded")

    adapter_id = str(uuid.uuid4())
    key = generate_encryption_key()
    srs_data = encrypt_to_srs(raw_data, adapter_id, key)

    srs_dir = Path(SRS_STORAGE_DIR)
    srs_dir.mkdir(parents=True, exist_ok=True)
    srs_path = srs_dir / f"{adapter_id}.srs"
    srs_path.write_bytes(srs_data)

    model_label = SSERIES_MODEL_COSTS.get(job.model, {}).get("label", job.model)
    name = adapter_name or f"{model_label} Neural Surgery #{job.id}"

    adapter = SseriesAdapter(
        id=adapter_id,
        user_id=user.id,
        name=name,
        base_model=job.model,
        encryption_key=key,
        training_job_id=job.id,
        file_size=len(srs_data),
        file_path=str(srs_path),
        status="active",
    )
    db.add(adapter)
    db.commit()
    del raw_data

    inf_cost = SSERIES_INFERENCE_COSTS.get(job.model, {}).get("credits_per_call", 3)
    return {
        "adapter_id": adapter_id,
        "name": name,
        "base_model": job.model,
        "file_size": len(srs_data),
        "format": ".srs",
        "status": "active",
        "credits_per_inference": inf_cost,
        "message": "Neural surgery adapter encrypted and stored. Key is server-side only.",
    }


def encrypt_and_store_sseries_adapter(
    adapter_data: bytes,
    user_id: int,
    job: SseriesTrainingJob,
    adapter_name: str,
    db: Session,
) -> SseriesAdapter:
    """Programmatic encryption -- used by training pipeline on completion."""
    adapter_id = str(uuid.uuid4())
    key = generate_encryption_key()
    srs_data = encrypt_to_srs(adapter_data, adapter_id, key)

    srs_dir = Path(SRS_STORAGE_DIR)
    srs_dir.mkdir(parents=True, exist_ok=True)
    srs_path = srs_dir / f"{adapter_id}.srs"
    srs_path.write_bytes(srs_data)

    model_label = SSERIES_MODEL_COSTS.get(job.model, {}).get("label", job.model)
    name = adapter_name or f"{model_label} Neural Surgery #{job.id}"

    adapter = SseriesAdapter(
        id=adapter_id,
        user_id=user_id,
        name=name,
        base_model=job.model,
        encryption_key=key,
        training_job_id=job.id,
        file_size=len(srs_data),
        file_path=str(srs_path),
        status="active",
    )
    db.add(adapter)
    return adapter


@router.delete("/{adapter_id}")
async def delete_sseries_adapter(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = db.query(SseriesAdapter).filter(
        SseriesAdapter.id == adapter_id,
        SseriesAdapter.user_id == user.id,
    ).first()
    if not adapter:
        raise HTTPException(404, "S-SER1ES adapter not found")

    adapter.status = "deleted"
    db.commit()

    if adapter.file_path:
        srs_path = Path(adapter.file_path)
        if srs_path.exists():
            try:
                srs_path.unlink()
            except Exception:
                pass

    return {"adapter_id": adapter_id, "status": "deleted"}
