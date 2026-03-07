"""Ogenti Platform — Adapter & Inference Routes

Endpoints:
  GET  /api/adapters           — List user's adapters
  GET  /api/adapters/{id}      — Get adapter details
  GET  /api/adapters/{id}/download — Download encrypted .ogt file
  POST /api/adapters/infer     — Run inference (decrypts server-side, charges credits)
  POST /api/adapters/encrypt   — Encrypt an uploaded safetensors → .ogt (internal/admin)
  GET  /api/adapters/pricing   — Inference pricing table
  DELETE /api/adapters/{id}    — Soft-delete adapter
"""

import uuid
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, Adapter, Transaction, TrainingJob
from .auth import get_current_user
from .config import INFERENCE_COSTS, MODEL_COSTS, OGT_STORAGE_DIR
from .ogt_crypto import (
    generate_encryption_key,
    encrypt_to_ogt,
    decrypt_ogt,
    get_ogt_info,
)

router = APIRouter(prefix="/api/adapters", tags=["adapters"])

# Ensure storage directory exists
Path(OGT_STORAGE_DIR).mkdir(parents=True, exist_ok=True)


# ── Schemas ──
class InferRequest(BaseModel):
    adapter_id: str
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7


class EncryptRequest(BaseModel):
    training_job_id: int
    adapter_name: str = ""


# ── Pricing ──
@router.get("/pricing")
async def inference_pricing():
    """Return per-call inference costs for each model."""
    result = []
    for model_id, info in INFERENCE_COSTS.items():
        model_meta = MODEL_COSTS.get(model_id, {})
        result.append({
            "model": model_id,
            "label": info["label"],
            "credits_per_call": info["credits_per_call"],
            "speed": model_meta.get("speed", "N/A"),
        })
    return {"pricing": result}


# ── List Adapters ──
@router.get("")
async def list_adapters(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all adapters owned by this user."""
    adapters = (
        db.query(Adapter)
        .filter(Adapter.user_id == user.id, Adapter.status != "deleted")
        .order_by(Adapter.created_at.desc())
        .all()
    )

    inf_costs = INFERENCE_COSTS
    return [
        {
            "id": a.id,
            "name": a.name,
            "base_model": a.base_model,
            "base_model_label": MODEL_COSTS.get(a.base_model, {}).get("label", a.base_model),
            "file_size": a.file_size,
            "status": a.status,
            "inference_count": a.inference_count,
            "credits_per_call": inf_costs.get(a.base_model, {}).get("credits_per_call", 1),
            "training_job_id": a.training_job_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in adapters
    ]


# ── Get Single Adapter ──
@router.get("/{adapter_id}")
async def get_adapter(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = db.query(Adapter).filter(
        Adapter.id == adapter_id,
        Adapter.user_id == user.id,
        Adapter.status != "deleted",
    ).first()
    if not adapter:
        raise HTTPException(404, "Adapter not found")

    inf_cost = INFERENCE_COSTS.get(adapter.base_model, {}).get("credits_per_call", 1)

    return {
        "id": adapter.id,
        "name": adapter.name,
        "base_model": adapter.base_model,
        "base_model_label": MODEL_COSTS.get(adapter.base_model, {}).get("label", adapter.base_model),
        "file_size": adapter.file_size,
        "status": adapter.status,
        "inference_count": adapter.inference_count,
        "credits_per_call": inf_cost,
        "training_job_id": adapter.training_job_id,
        "created_at": adapter.created_at.isoformat() if adapter.created_at else None,
    }


# ── Download .ogt (encrypted — useless without server key) ──
@router.get("/{adapter_id}/download")
async def download_ogt(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download the encrypted .ogt file. It cannot be decrypted without our server."""
    adapter = db.query(Adapter).filter(
        Adapter.id == adapter_id,
        Adapter.user_id == user.id,
        Adapter.status == "active",
    ).first()
    if not adapter:
        raise HTTPException(404, "Adapter not found")

    ogt_path = Path(adapter.file_path) if adapter.file_path else None
    if not ogt_path or not ogt_path.exists():
        raise HTTPException(404, "Adapter file not found on server")

    def iter_file():
        with open(ogt_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    # Determine extension from stored file path
    stored_ext = Path(adapter.file_path).suffix if adapter.file_path else ".ogt"
    filename = f"{adapter.name.replace(' ', '_')}_{adapter.id[:8]}{stored_ext}"
    return StreamingResponse(
        iter_file(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Inference ──
@router.post("/infer")
async def run_inference(
    req: InferRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run inference using a decrypted adapter. Charges credits per call.

    Flow:
    1. Validate adapter belongs to user
    2. Check credit balance
    3. Decrypt .ogt in memory (key from DB)
    4. Run inference (stub — will connect to actual inference backend)
    5. Deduct credits & log transaction
    6. Return result
    """
    # 1. Find adapter
    adapter = db.query(Adapter).filter(
        Adapter.id == req.adapter_id,
        Adapter.user_id == user.id,
        Adapter.status == "active",
    ).first()
    if not adapter:
        raise HTTPException(404, "Adapter not found")

    # 2. Calculate cost
    cost_info = INFERENCE_COSTS.get(adapter.base_model, {"credits_per_call": 1})
    credits_needed = cost_info["credits_per_call"]

    if user.credits < credits_needed:
        raise HTTPException(
            402,
            f"Not enough credits. Need {credits_needed}, have {user.credits}. Buy more credits.",
        )

    # 3. Decrypt adapter (verify file exists & key works)
    ogt_path = Path(adapter.file_path) if adapter.file_path else None
    if not ogt_path or not ogt_path.exists():
        raise HTTPException(500, "Adapter file not found on server")

    try:
        ogt_data = ogt_path.read_bytes()
        adapter_id_check, safetensors_data = decrypt_ogt(ogt_data, adapter.encryption_key)
    except ValueError as e:
        raise HTTPException(500, f"Adapter decryption failed: {e}")

    # 4. Run inference — STUB for now, will integrate actual inference engine
    #    In production this sends safetensors_data to GPU worker
    model_label = MODEL_COSTS.get(adapter.base_model, {}).get("label", adapter.base_model)
    result_text = (
        f"[Ogenti Inference] Model: {model_label} | "
        f"Adapter: {adapter.name} | "
        f"Prompt: {req.prompt[:100]}... | "
        f"(Inference engine integration pending — adapter decrypted successfully, "
        f"{len(safetensors_data):,} bytes loaded)"
    )

    # 5. Deduct credits
    user.credits -= credits_needed
    adapter.inference_count += 1

    txn = Transaction(
        user_id=user.id,
        type="inference",
        credits=-credits_needed,
        description=f"Inference: {adapter.name} ({model_label})",
    )
    db.add(txn)
    db.commit()

    return {
        "adapter_id": adapter.id,
        "adapter_name": adapter.name,
        "model": adapter.base_model,
        "model_label": model_label,
        "result": result_text,
        "credits_used": credits_needed,
        "remaining_credits": user.credits,
        "inference_count": adapter.inference_count,
    }


# ── Encrypt Safetensors → .ogt (called after training completes) ──
@router.post("/encrypt")
async def encrypt_adapter(
    training_job_id: int = Form(...),
    adapter_name: str = Form(""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a safetensors file, encrypt it to .ogt, store key server-side.

    This is called automatically when training completes, or manually by admin.
    The uploaded safetensors is immediately encrypted and the plaintext is discarded.
    """
    # Validate training job
    job = db.query(TrainingJob).filter(
        TrainingJob.id == training_job_id,
        TrainingJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(404, "Training job not found")

    # Check if adapter already exists for this job
    existing = db.query(Adapter).filter(Adapter.training_job_id == training_job_id).first()
    if existing:
        raise HTTPException(409, "Adapter already exists for this training job")

    # Read uploaded file
    raw_data = await file.read()
    if len(raw_data) == 0:
        raise HTTPException(400, "Empty file uploaded")

    # Generate adapter ID and encryption key
    adapter_id = str(uuid.uuid4())
    key = generate_encryption_key()

    # Encrypt
    ogt_data = encrypt_to_ogt(raw_data, adapter_id, key)

    # Save .ogt file
    ogt_dir = Path(OGT_STORAGE_DIR)
    ogt_dir.mkdir(parents=True, exist_ok=True)
    ogt_path = ogt_dir / f"{adapter_id}.ogt"
    ogt_path.write_bytes(ogt_data)

    # Create adapter record (key stored in DB, never sent to client)
    model_label = MODEL_COSTS.get(job.model, {}).get("label", job.model)
    name = adapter_name or f"{model_label} Adapter #{job.id}"

    adapter = Adapter(
        id=adapter_id,
        user_id=user.id,
        name=name,
        base_model=job.model,
        encryption_key=key,
        training_job_id=job.id,
        file_size=len(ogt_data),
        file_path=str(ogt_path),
        status="active",
    )
    db.add(adapter)
    db.commit()

    # Clean up plaintext from memory
    del raw_data

    inf_cost = INFERENCE_COSTS.get(job.model, {}).get("credits_per_call", 1)

    return {
        "adapter_id": adapter_id,
        "name": name,
        "base_model": job.model,
        "model_label": model_label,
        "file_size": len(ogt_data),
        "format": ".ogt (AES-256-GCM encrypted)",
        "credits_per_inference": inf_cost,
        "message": f"Adapter encrypted and stored. Adapter key is server-side only. "
                   f"The .ogt file is useless without Ogenti's server.",
    }


# ── Internal: Encrypt from safetensors bytes (called by training pipeline) ──
def encrypt_and_store_adapter(
    safetensors_data: bytes,
    user_id: int,
    job: TrainingJob,
    adapter_name: str,
    db: Session,
    adapter_ext: str = ".ogt",
    products: list = None,
    training_mode: str = "v1",
) -> Adapter:
    """Programmatic encryption — used by training pipeline when job completes.

    Args:
        adapter_ext: File extension (.ogt/.oge/.phr/.prh/.mrh/.syh/.ser)
        products: List of products this adapter covers
        training_mode: "v1" or "v2"

    Returns: created Adapter object
    """
    adapter_id = str(uuid.uuid4())
    key = generate_encryption_key()

    ogt_data = encrypt_to_ogt(safetensors_data, adapter_id, key)

    ogt_dir = Path(OGT_STORAGE_DIR)
    ogt_dir.mkdir(parents=True, exist_ok=True)
    ogt_path = ogt_dir / f"{adapter_id}{adapter_ext}"
    ogt_path.write_bytes(ogt_data)

    model_label = MODEL_COSTS.get(job.model, {}).get("label", job.model)
    name = adapter_name or f"{model_label} Adapter #{job.id}"

    adapter = Adapter(
        id=adapter_id,
        user_id=user_id,
        name=name,
        base_model=job.model,
        encryption_key=key,
        training_job_id=job.id,
        file_size=len(ogt_data),
        file_path=str(ogt_path),
        status="active",
    )
    db.add(adapter)

    return adapter


# ── Soft-delete ──
@router.delete("/{adapter_id}")
async def delete_adapter(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = db.query(Adapter).filter(
        Adapter.id == adapter_id,
        Adapter.user_id == user.id,
    ).first()
    if not adapter:
        raise HTTPException(404, "Adapter not found")

    adapter.status = "deleted"
    db.commit()

    # Optionally delete .ogt file from disk
    ogt_path = Path(adapter.file_path) if adapter.file_path else None
    if ogt_path and ogt_path.exists():
        ogt_path.unlink(missing_ok=True)

    return {"message": "Adapter deleted", "adapter_id": adapter_id}
