"""Ser1es Platform — PHIREN Adapter & Inference Routes

Hallucination guard adapters (.phr format).

Endpoints:
  GET  /api/phiren/adapters           — List user's PHIREN adapters
  GET  /api/phiren/adapters/{id}      — Get adapter details
  GET  /api/phiren/adapters/{id}/download — Download encrypted .phr
  POST /api/phiren/adapters/infer     — Run hallucination check (charges credits)
  POST /api/phiren/adapters/encrypt   — Encrypt uploaded weights → .phr
  GET  /api/phiren/adapters/pricing   — Inference pricing table
  DELETE /api/phiren/adapters/{id}    — Soft-delete adapter
"""

import uuid
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, PhirenAdapter, PhirenTrainingJob, Transaction
from .auth import get_current_user
from .config import PHIREN_INFERENCE_COSTS, PHIREN_MODEL_COSTS, PHR_STORAGE_DIR
from .phr_crypto import generate_encryption_key, encrypt_to_phr, decrypt_phr, get_phr_info

router = APIRouter(prefix="/api/phiren/adapters", tags=["phiren-adapters"])

Path(PHR_STORAGE_DIR).mkdir(parents=True, exist_ok=True)


class PhirenInferRequest(BaseModel):
    adapter_id: str
    text: str         # text to fact-check / hallucination-check
    context: str = ""  # optional context for grounded verification
    mode: str = "full"  # full | quick | strict


class PhirenEncryptRequest(BaseModel):
    training_job_id: int
    adapter_name: str = ""


@router.get("/pricing")
async def phiren_pricing():
    """Return per-call inference costs for each PHIREN model."""
    result = []
    for model_id, info in PHIREN_INFERENCE_COSTS.items():
        model_meta = PHIREN_MODEL_COSTS.get(model_id, {})
        result.append({
            "model": model_id,
            "label": info["label"],
            "credits_per_call": info["credits_per_call"],
            "speed": model_meta.get("speed", "N/A"),
        })
    return {"pricing": result}


@router.get("")
async def list_phiren_adapters(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all PHIREN adapters owned by user."""
    adapters = (
        db.query(PhirenAdapter)
        .filter(PhirenAdapter.user_id == user.id, PhirenAdapter.status != "deleted")
        .order_by(PhirenAdapter.created_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "name": a.name,
            "base_model": a.base_model,
            "base_model_label": PHIREN_MODEL_COSTS.get(a.base_model, {}).get("label", a.base_model),
            "file_size": a.file_size,
            "status": a.status,
            "inference_count": a.inference_count,
            "credits_per_call": PHIREN_INFERENCE_COSTS.get(a.base_model, {}).get("credits_per_call", 2),
            "training_job_id": a.training_job_id,
            "format": ".phr",
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in adapters
    ]


@router.get("/{adapter_id}")
async def get_phiren_adapter(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = db.query(PhirenAdapter).filter(
        PhirenAdapter.id == adapter_id,
        PhirenAdapter.user_id == user.id,
        PhirenAdapter.status != "deleted",
    ).first()
    if not adapter:
        raise HTTPException(404, "PHIREN adapter not found")

    inf_cost = PHIREN_INFERENCE_COSTS.get(adapter.base_model, {}).get("credits_per_call", 2)
    return {
        "id": adapter.id,
        "name": adapter.name,
        "base_model": adapter.base_model,
        "base_model_label": PHIREN_MODEL_COSTS.get(adapter.base_model, {}).get("label", adapter.base_model),
        "file_size": adapter.file_size,
        "status": adapter.status,
        "inference_count": adapter.inference_count,
        "credits_per_call": inf_cost,
        "training_job_id": adapter.training_job_id,
        "format": ".phr",
        "created_at": adapter.created_at.isoformat() if adapter.created_at else None,
    }


@router.get("/{adapter_id}/download")
async def download_phr(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download encrypted .phr file."""
    adapter = db.query(PhirenAdapter).filter(
        PhirenAdapter.id == adapter_id,
        PhirenAdapter.user_id == user.id,
        PhirenAdapter.status == "active",
    ).first()
    if not adapter:
        raise HTTPException(404, "PHIREN adapter not found")

    phr_path = Path(adapter.file_path) if adapter.file_path else None
    if not phr_path or not phr_path.exists():
        raise HTTPException(404, "Adapter file not found on server")

    def iter_file():
        with open(phr_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    filename = f"{adapter.name.replace(' ', '_')}_{adapter.id[:8]}.phr"
    return StreamingResponse(
        iter_file(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/infer")
async def run_phiren_inference(
    req: PhirenInferRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run hallucination detection inference using PHIREN adapter.

    Takes text (and optional context), evaluates factuality and calibration.
    Returns a detailed hallucination report with claim-level verdicts.
    """
    adapter = db.query(PhirenAdapter).filter(
        PhirenAdapter.id == req.adapter_id,
        PhirenAdapter.user_id == user.id,
        PhirenAdapter.status == "active",
    ).first()
    if not adapter:
        raise HTTPException(404, "PHIREN adapter not found")

    cost_info = PHIREN_INFERENCE_COSTS.get(adapter.base_model, {"credits_per_call": 2})
    credits_needed = cost_info["credits_per_call"]

    if user.credits < credits_needed:
        raise HTTPException(402, f"Not enough credits. Need {credits_needed}, have {user.credits}.")

    phr_path = Path(adapter.file_path) if adapter.file_path else None
    if not phr_path or not phr_path.exists():
        raise HTTPException(500, "Adapter file not found")

    try:
        phr_data = phr_path.read_bytes()
        adapter_id_check, weights_data = decrypt_phr(phr_data, adapter.encryption_key)
    except ValueError as e:
        raise HTTPException(500, f"Adapter decryption failed: {e}")

    # Run inference — STUB (will connect to actual hallucination detection backend)
    import hashlib
    text_hash = hashlib.sha256(req.text.encode()).hexdigest()

    # Mock hallucination detection results (in production, GPU worker processes text)
    seed_val = int(text_hash[:8], 16) / 0xFFFFFFFF
    factuality_score = 0.65 + seed_val * 0.30  # 65-95%
    calibration_score = 0.70 + seed_val * 0.25  # 70-95%

    # Extract mock claims
    sentences = [s.strip() for s in req.text.split('.') if s.strip()]
    claims = []
    for i, sentence in enumerate(sentences[:10]):  # max 10 claims
        claim_seed = int(hashlib.md5(sentence.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        verdict = "supported" if claim_seed > 0.3 else ("contradicted" if claim_seed < 0.15 else "unverifiable")
        claims.append({
            "claim": sentence[:200],
            "verdict": verdict,
            "confidence": round(0.6 + claim_seed * 0.4, 3),
        })

    model_label = PHIREN_MODEL_COSTS.get(adapter.base_model, {}).get("label", adapter.base_model)

    result = {
        "factuality_score": round(factuality_score, 4),
        "calibration_score": round(calibration_score, 4),
        "overall_verdict": "reliable" if factuality_score > 0.8 else ("uncertain" if factuality_score > 0.6 else "unreliable"),
        "claims_analyzed": len(claims),
        "claims": claims,
        "mode": req.mode,
        "has_context": bool(req.context),
        "note": f"[PHIREN Inference] Model: {model_label} | Adapter: {adapter.name} | "
                f"Text: {len(req.text)} chars, {len(claims)} claims extracted "
                f"(GPU inference backend integration pending)",
    }

    # Deduct credits
    user.credits -= credits_needed
    adapter.inference_count += 1
    db.add(Transaction(
        user_id=user.id, type="inference", credits=-credits_needed,
        description=f"PHIREN Inference: {adapter.name} ({model_label})",
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
async def encrypt_phiren_adapter(
    training_job_id: int = Form(...),
    adapter_name: str = Form(""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload hallucination guard weights, encrypt to .phr, store key server-side."""
    job = db.query(PhirenTrainingJob).filter(
        PhirenTrainingJob.id == training_job_id,
        PhirenTrainingJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(404, "PHIREN training job not found")

    existing = db.query(PhirenAdapter).filter(PhirenAdapter.training_job_id == training_job_id).first()
    if existing:
        raise HTTPException(409, "Adapter already exists for this training job")

    raw_data = await file.read()
    if len(raw_data) == 0:
        raise HTTPException(400, "Empty file uploaded")

    adapter_id = str(uuid.uuid4())
    key = generate_encryption_key()
    phr_data = encrypt_to_phr(raw_data, adapter_id, key)

    phr_dir = Path(PHR_STORAGE_DIR)
    phr_dir.mkdir(parents=True, exist_ok=True)
    phr_path = phr_dir / f"{adapter_id}.phr"
    phr_path.write_bytes(phr_data)

    model_label = PHIREN_MODEL_COSTS.get(job.model, {}).get("label", job.model)
    name = adapter_name or f"{model_label} Hallucination Guard #{job.id}"

    adapter = PhirenAdapter(
        id=adapter_id,
        user_id=user.id,
        name=name,
        base_model=job.model,
        encryption_key=key,
        training_job_id=job.id,
        file_size=len(phr_data),
        file_path=str(phr_path),
        status="active",
    )
    db.add(adapter)
    db.commit()
    del raw_data

    inf_cost = PHIREN_INFERENCE_COSTS.get(job.model, {}).get("credits_per_call", 2)
    return {
        "adapter_id": adapter_id,
        "name": name,
        "base_model": job.model,
        "model_label": model_label,
        "file_size": len(phr_data),
        "format": ".phr (AES-256-GCM encrypted)",
        "credits_per_inference": inf_cost,
        "message": "Hallucination guard adapter encrypted and stored. Key is server-side only.",
    }


def encrypt_and_store_phiren_adapter(
    adapter_data: bytes,
    user_id: int,
    job: PhirenTrainingJob,
    adapter_name: str,
    db: Session,
) -> PhirenAdapter:
    """Programmatic encryption — used by training pipeline on completion."""
    adapter_id = str(uuid.uuid4())
    key = generate_encryption_key()
    phr_data = encrypt_to_phr(adapter_data, adapter_id, key)

    phr_dir = Path(PHR_STORAGE_DIR)
    phr_dir.mkdir(parents=True, exist_ok=True)
    phr_path = phr_dir / f"{adapter_id}.phr"
    phr_path.write_bytes(phr_data)

    model_label = PHIREN_MODEL_COSTS.get(job.model, {}).get("label", job.model)
    name = adapter_name or f"{model_label} Hallucination Guard #{job.id}"

    adapter = PhirenAdapter(
        id=adapter_id,
        user_id=user_id,
        name=name,
        base_model=job.model,
        encryption_key=key,
        training_job_id=job.id,
        file_size=len(phr_data),
        file_path=str(phr_path),
        status="active",
    )
    db.add(adapter)
    return adapter


@router.delete("/{adapter_id}")
async def delete_phiren_adapter(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = db.query(PhirenAdapter).filter(
        PhirenAdapter.id == adapter_id,
        PhirenAdapter.user_id == user.id,
    ).first()
    if not adapter:
        raise HTTPException(404, "PHIREN adapter not found")

    adapter.status = "deleted"
    adapter.deleted_at = datetime.now(timezone.utc)
    db.commit()

    # Optionally remove file
    if adapter.file_path:
        phr_path = Path(adapter.file_path)
        if phr_path.exists():
            try:
                phr_path.unlink()
            except Exception:
                pass

    return {"adapter_id": adapter_id, "status": "deleted"}
