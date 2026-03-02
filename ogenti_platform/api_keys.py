"""Ogenti Platform — API Key Management Routes"""
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, ApiKey
from .auth import get_current_user, generate_api_key

router = APIRouter(prefix="/api/keys", tags=["api_keys"])


class CreateKeyRequest(BaseModel):
    name: str = "New Key"

class RevokeKeyRequest(BaseModel):
    key_id: int


@router.get("/list")
async def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List all API keys for user"""
    keys = (
        db.query(ApiKey)
        .filter(ApiKey.user_id == user.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return [
        {
            "id": k.id,
            "key_prefix": k.key_prefix,
            "name": k.name,
            "active": k.active,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used": k.last_used.isoformat() if k.last_used else None,
        }
        for k in keys
    ]


@router.post("/create")
async def create_key(req: CreateKeyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate a new API key"""
    # Max 5 keys per user
    count = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.active == True).count()
    if count >= 5:
        raise HTTPException(400, "Maximum 5 active API keys allowed")

    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(user_id=user.id, key_hash=key_hash, key_prefix=prefix, name=req.name)
    db.add(api_key)
    db.commit()

    return {
        "key": full_key,
        "key_prefix": prefix,
        "name": req.name,
        "id": api_key.id,
    }


@router.post("/revoke")
async def revoke_key(req: RevokeKeyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke an API key"""
    key = db.query(ApiKey).filter(ApiKey.id == req.key_id, ApiKey.user_id == user.id).first()
    if not key:
        raise HTTPException(404, "Key not found")
    key.active = False
    db.commit()
    return {"message": "Key revoked", "key_id": req.key_id}
