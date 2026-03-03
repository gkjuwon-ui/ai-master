"""O Series Platform — OVISEN Adapter & Inference Routes

Image embedding compression adapters (.oge format).

Endpoints:
  GET  /api/ovisen/adapters           — List user's vision adapters
  GET  /api/ovisen/adapters/{id}      — Get adapter details
  GET  /api/ovisen/adapters/{id}/download — Download encrypted .oge
  POST /api/ovisen/adapters/infer     — Run image embedding inference (charges credits)
  POST /api/ovisen/adapters/encrypt   — Encrypt uploaded weights → .oge
  GET  /api/ovisen/adapters/pricing   — Inference pricing table
  DELETE /api/ovisen/adapters/{id}    — Soft-delete adapter
"""

import uuid
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, OVisenAdapter, OVisenTrainingJob, Transaction
from .auth import get_current_user
from .config import OVISEN_INFERENCE_COSTS, OVISEN_MODEL_COSTS, OGE_STORAGE_DIR
from .oge_crypto import generate_encryption_key, encrypt_to_oge, decrypt_oge, get_oge_info

router = APIRouter(prefix="/api/ovisen/adapters", tags=["ovisen-adapters"])

Path(OGE_STORAGE_DIR).mkdir(parents=True, exist_ok=True)


class OVisenInferRequest(BaseModel):
    adapter_id: str
    image_base64: str  # base64-encoded input image
    target_dim: int = 256  # target embedding dimension
    format: str = "float32"  # output format


class OVisenEncryptRequest(BaseModel):
    training_job_id: int
    adapter_name: str = ""


@router.get("/pricing")
async def ovisen_pricing():
    """Return per-call inference costs for each vision model."""
    result = []
    for model_id, info in OVISEN_INFERENCE_COSTS.items():
        model_meta = OVISEN_MODEL_COSTS.get(model_id, {})
        result.append({
            "model": model_id,
            "label": info["label"],
            "credits_per_call": info["credits_per_call"],
            "speed": model_meta.get("speed", "N/A"),
        })
    return {"pricing": result}


@router.get("")
async def list_ovisen_adapters(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all OVISEN adapters owned by user."""
    adapters = (
        db.query(OVisenAdapter)
        .filter(OVisenAdapter.user_id == user.id, OVisenAdapter.status != "deleted")
        .order_by(OVisenAdapter.created_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "name": a.name,
            "base_model": a.base_model,
            "base_model_label": OVISEN_MODEL_COSTS.get(a.base_model, {}).get("label", a.base_model),
            "file_size": a.file_size,
            "status": a.status,
            "inference_count": a.inference_count,
            "credits_per_call": OVISEN_INFERENCE_COSTS.get(a.base_model, {}).get("credits_per_call", 2),
            "training_job_id": a.training_job_id,
            "format": ".oge",
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in adapters
    ]


@router.get("/{adapter_id}")
async def get_ovisen_adapter(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = db.query(OVisenAdapter).filter(
        OVisenAdapter.id == adapter_id,
        OVisenAdapter.user_id == user.id,
        OVisenAdapter.status != "deleted",
    ).first()
    if not adapter:
        raise HTTPException(404, "OVISEN adapter not found")

    inf_cost = OVISEN_INFERENCE_COSTS.get(adapter.base_model, {}).get("credits_per_call", 2)
    return {
        "id": adapter.id,
        "name": adapter.name,
        "base_model": adapter.base_model,
        "base_model_label": OVISEN_MODEL_COSTS.get(adapter.base_model, {}).get("label", adapter.base_model),
        "file_size": adapter.file_size,
        "status": adapter.status,
        "inference_count": adapter.inference_count,
        "credits_per_call": inf_cost,
        "training_job_id": adapter.training_job_id,
        "format": ".oge",
        "created_at": adapter.created_at.isoformat() if adapter.created_at else None,
    }


@router.get("/{adapter_id}/download")
async def download_oge(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download encrypted .oge file."""
    adapter = db.query(OVisenAdapter).filter(
        OVisenAdapter.id == adapter_id,
        OVisenAdapter.user_id == user.id,
        OVisenAdapter.status == "active",
    ).first()
    if not adapter:
        raise HTTPException(404, "OVISEN adapter not found")

    oge_path = Path(adapter.file_path) if adapter.file_path else None
    if not oge_path or not oge_path.exists():
        raise HTTPException(404, "Adapter file not found on server")

    def iter_file():
        with open(oge_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    filename = f"{adapter.name.replace(' ', '_')}_{adapter.id[:8]}.oge"
    return StreamingResponse(
        iter_file(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/infer")
async def run_ovisen_inference(
    req: OVisenInferRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run image → embedding inference using OVISEN adapter.

    Takes a base64-encoded image, converts it to a compressed high-dimensional
    embedding using the trained vision adapter. The output embedding can be
    directly consumed by any downstream AI agent without needing the original image.
    """
    adapter = db.query(OVisenAdapter).filter(
        OVisenAdapter.id == req.adapter_id,
        OVisenAdapter.user_id == user.id,
        OVisenAdapter.status == "active",
    ).first()
    if not adapter:
        raise HTTPException(404, "OVISEN adapter not found")

    cost_info = OVISEN_INFERENCE_COSTS.get(adapter.base_model, {"credits_per_call": 2})
    credits_needed = cost_info["credits_per_call"]

    if user.credits < credits_needed:
        raise HTTPException(402, f"Not enough credits. Need {credits_needed}, have {user.credits}.")

    oge_path = Path(adapter.file_path) if adapter.file_path else None
    if not oge_path or not oge_path.exists():
        raise HTTPException(500, "Adapter file not found")

    try:
        oge_data = oge_path.read_bytes()
        adapter_id_check, weights_data = decrypt_oge(oge_data, adapter.encryption_key)
    except ValueError as e:
        raise HTTPException(500, f"Adapter decryption failed: {e}")

    # Run inference — STUB (will connect to actual vision inference backend)
    import base64
    try:
        image_bytes = base64.b64decode(req.image_base64)
        image_size = len(image_bytes)
    except Exception:
        raise HTTPException(400, "Invalid base64 image data")

    model_label = OVISEN_MODEL_COSTS.get(adapter.base_model, {}).get("label", adapter.base_model)

    # Generate mock embedding (in production, GPU worker processes the image)
    import hashlib
    seed = hashlib.sha256(image_bytes[:1024]).digest()
    embedding_preview = [round(b / 255.0 * 2 - 1, 4) for b in seed[:min(req.target_dim, 32)]]

    result = {
        "embedding_dim": req.target_dim,
        "embedding_preview": embedding_preview,
        "compression_ratio": round(image_size / (req.target_dim * 4), 1),  # float32 = 4 bytes per dim
        "original_image_size": image_size,
        "compressed_size": req.target_dim * 4,
        "format": req.format,
        "note": f"[OVISEN Inference] Model: {model_label} | Adapter: {adapter.name} | "
                f"Image: {image_size:,} bytes → {req.target_dim}-dim embedding "
                f"(GPU inference backend integration pending)",
    }

    # Deduct credits
    user.credits -= credits_needed
    adapter.inference_count += 1
    db.add(Transaction(
        user_id=user.id, type="inference", credits=-credits_needed,
        description=f"OVISEN Inference: {adapter.name} ({model_label})",
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
async def encrypt_ovisen_adapter(
    training_job_id: int = Form(...),
    adapter_name: str = Form(""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload vision adapter weights, encrypt to .oge, store key server-side."""
    job = db.query(OVisenTrainingJob).filter(
        OVisenTrainingJob.id == training_job_id,
        OVisenTrainingJob.user_id == user.id,
    ).first()
    if not job:
        raise HTTPException(404, "OVISEN training job not found")

    existing = db.query(OVisenAdapter).filter(OVisenAdapter.training_job_id == training_job_id).first()
    if existing:
        raise HTTPException(409, "Adapter already exists for this training job")

    raw_data = await file.read()
    if len(raw_data) == 0:
        raise HTTPException(400, "Empty file uploaded")

    adapter_id = str(uuid.uuid4())
    key = generate_encryption_key()
    oge_data = encrypt_to_oge(raw_data, adapter_id, key)

    oge_dir = Path(OGE_STORAGE_DIR)
    oge_dir.mkdir(parents=True, exist_ok=True)
    oge_path = oge_dir / f"{adapter_id}.oge"
    oge_path.write_bytes(oge_data)

    model_label = OVISEN_MODEL_COSTS.get(job.model, {}).get("label", job.model)
    name = adapter_name or f"{model_label} Vision Adapter #{job.id}"

    adapter = OVisenAdapter(
        id=adapter_id,
        user_id=user.id,
        name=name,
        base_model=job.model,
        encryption_key=key,
        training_job_id=job.id,
        file_size=len(oge_data),
        file_path=str(oge_path),
        status="active",
    )
    db.add(adapter)
    db.commit()
    del raw_data

    inf_cost = OVISEN_INFERENCE_COSTS.get(job.model, {}).get("credits_per_call", 2)
    return {
        "adapter_id": adapter_id,
        "name": name,
        "base_model": job.model,
        "model_label": model_label,
        "file_size": len(oge_data),
        "format": ".oge (AES-256-GCM encrypted)",
        "credits_per_inference": inf_cost,
        "message": f"Vision adapter encrypted and stored. Key is server-side only.",
    }


def encrypt_and_store_ovisen_adapter(
    adapter_data: bytes,
    user_id: int,
    job: OVisenTrainingJob,
    adapter_name: str,
    db: Session,
) -> OVisenAdapter:
    """Programmatic encryption — used by training pipeline on completion."""
    adapter_id = str(uuid.uuid4())
    key = generate_encryption_key()
    oge_data = encrypt_to_oge(adapter_data, adapter_id, key)

    oge_dir = Path(OGE_STORAGE_DIR)
    oge_dir.mkdir(parents=True, exist_ok=True)
    oge_path = oge_dir / f"{adapter_id}.oge"
    oge_path.write_bytes(oge_data)

    model_label = OVISEN_MODEL_COSTS.get(job.model, {}).get("label", job.model)
    name = adapter_name or f"{model_label} Vision Adapter #{job.id}"

    adapter = OVisenAdapter(
        id=adapter_id,
        user_id=user_id,
        name=name,
        base_model=job.model,
        encryption_key=key,
        training_job_id=job.id,
        file_size=len(oge_data),
        file_path=str(oge_path),
        status="active",
    )
    db.add(adapter)
    return adapter


@router.delete("/{adapter_id}")
async def delete_ovisen_adapter(
    adapter_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    adapter = db.query(OVisenAdapter).filter(
        OVisenAdapter.id == adapter_id,
        OVisenAdapter.user_id == user.id,
    ).first()
    if not adapter:
        raise HTTPException(404, "OVISEN adapter not found")

    adapter.status = "deleted"
    db.commit()

    oge_path = Path(adapter.file_path) if adapter.file_path else None
    if oge_path and oge_path.exists():
        oge_path.unlink(missing_ok=True)

    return {"message": "OVISEN adapter deleted", "adapter_id": adapter_id}
