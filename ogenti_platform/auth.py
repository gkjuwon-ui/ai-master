"""Ogenti Platform — Auth Routes"""
import secrets
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from typing import Optional
from passlib.context import CryptContext
from jose import jwt
from sqlalchemy.orm import Session

from .database import get_db, User, VerificationCode, ApiKey
from .email_service import send_verification_email, generate_code, get_code_expiry
from .config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, TIERS

router = APIRouter(prefix="/api/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Schemas ──
class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""

class VerifyRequest(BaseModel):
    email: str
    code: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ResendRequest(BaseModel):
    email: str


# ── Helpers ──
def create_token(user_id: int, email: str) -> str:
    from datetime import timedelta
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "email": email, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> User:
    """Extract JWT from Authorization header and return user"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def generate_api_key() -> tuple[str, str, str]:
    """Generate API key → (full_key, prefix, hash)"""
    raw = f"og_{secrets.token_hex(24)}"
    prefix = raw[:12] + "..."
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, prefix, key_hash


# ── Routes ──
@router.post("/signup")
async def signup(req: SignupRequest, db: Session = Depends(get_db)):
    """Step 1: Register email + send verification code"""
    existing = db.query(User).filter(User.email == req.email).first()
    if existing and existing.email_verified:
        raise HTTPException(400, "Email already registered")

    # Remove unverified user if exists
    if existing and not existing.email_verified:
        db.delete(existing)
        db.commit()

    # Create unverified user
    user = User(
        email=req.email,
        password_hash=pwd_context.hash(req.password),
        name=req.name,
        tier="free",
        credits=100,
        email_verified=False,
    )
    db.add(user)
    db.commit()

    # Generate and save verification code
    code = generate_code()
    vc = VerificationCode(email=req.email, code=code, expires_at=get_code_expiry())
    db.add(vc)
    db.commit()

    # Send email
    sent = await send_verification_email(req.email, code)
    if not sent:
        raise HTTPException(500, "Failed to send verification email. Please try again.")

    return {"message": "Verification code sent", "email": req.email}


@router.post("/verify")
async def verify_email(req: VerifyRequest, db: Session = Depends(get_db)):
    """Step 2: Verify email with code → return JWT"""
    vc = (
        db.query(VerificationCode)
        .filter(
            VerificationCode.email == req.email,
            VerificationCode.code == req.code,
            VerificationCode.used == False,
        )
        .order_by(VerificationCode.id.desc())
        .first()
    )

    if not vc:
        raise HTTPException(400, "Invalid verification code")

    if vc.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, "Verification code expired")

    # Mark code as used
    vc.used = True

    # Verify user
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(400, "User not found")
    user.email_verified = True

    # Generate default API key
    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(user_id=user.id, key_hash=key_hash, key_prefix=prefix, name="Default Key")
    db.add(api_key)
    db.commit()

    token = create_token(user.id, user.email)
    return {
        "token": token,
        "api_key": full_key,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "tier": user.tier,
            "credits": user.credits,
        },
    }


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Login with email + password → JWT"""
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.email_verified:
        raise HTTPException(403, "Email not verified. Check your inbox.")

    token = create_token(user.id, user.email)
    return {
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "tier": user.tier,
            "credits": user.credits,
        },
    }


@router.post("/resend-code")
async def resend_code(req: ResendRequest, db: Session = Depends(get_db)):
    """Resend verification code"""
    code = generate_code()
    vc = VerificationCode(email=req.email, code=code, expires_at=get_code_expiry())
    db.add(vc)
    db.commit()
    sent = await send_verification_email(req.email, code)
    if not sent:
        raise HTTPException(500, "Failed to send verification email. Please try again.")
    return {"message": "New code sent"}


@router.get("/me")
async def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get current user info"""
    tier_info = TIERS.get(user.tier, TIERS["free"])
    keys = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.active == True).count()
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "tier": user.tier,
        "tier_label": tier_info["label"],
        "credits": user.credits,
        "email_verified": user.email_verified,
        "api_key_count": keys,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
