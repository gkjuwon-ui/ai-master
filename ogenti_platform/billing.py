"""Ogenti Platform — Billing & Credits Routes"""
import stripe
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db, User, Transaction
from .auth import get_current_user
from .config import (
    STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET,
    CREDIT_PACKAGES, MODEL_COSTS, TIERS,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])
stripe.api_key = STRIPE_SECRET_KEY


# ── Schemas ──
class PurchaseRequest(BaseModel):
    package_id: str

class EstimateRequest(BaseModel):
    model: str
    episodes: int


# ── Routes ──
@router.get("/packages")
async def list_packages():
    """List available credit packages"""
    return CREDIT_PACKAGES


@router.get("/models")
async def list_models():
    """List available models with pricing"""
    result = []
    for name, info in MODEL_COSTS.items():
        result.append({"name": name, "credits_per_episode": info["credits_per_episode"], "label": info["label"], "vram": info["vram"], "speed": info["speed"]})
    return result


@router.get("/tiers")
async def list_tiers():
    """List subscription tiers"""
    result = []
    for name, info in TIERS.items():
        models_available = len(MODEL_COSTS) if info["models"] == "all" else len(info["models"])
        result.append({"name": name, "label": info["label"], "credits_required": 0, "models_available": models_available, "max_credits": info["monthly_credits"]})
    return result


@router.post("/estimate")
async def estimate_cost(req: EstimateRequest):
    """Estimate credits for a training job"""
    model_info = MODEL_COSTS.get(req.model)
    if not model_info:
        raise HTTPException(400, f"Unknown model: {req.model}")

    credits_needed = req.episodes * model_info["credits_per_episode"]

    # Find cheapest package that covers it
    best_package = None
    for pkg in sorted(CREDIT_PACKAGES, key=lambda p: p["credits"]):
        if pkg["credits"] >= credits_needed:
            best_package = pkg
            break
    if not best_package:
        best_package = CREDIT_PACKAGES[-1]  # biggest package

    return {
        "model": req.model,
        "model_label": model_info["label"],
        "episodes": req.episodes,
        "credits_per_episode": model_info["credits_per_episode"],
        "total_credits": credits_needed,
        "suggested_package": best_package,
    }


@router.post("/purchase")
async def purchase_credits(req: PurchaseRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Purchase credits via Stripe (test mode)"""

    # Find package
    package = next((p for p in CREDIT_PACKAGES if p["id"] == req.package_id), None)
    if not package:
        raise HTTPException(400, "Invalid package")

    try:
        # Create Stripe PaymentIntent (test mode)
        intent = stripe.PaymentIntent.create(
            amount=package["price_cents"],
            currency="usd",
            metadata={
                "user_id": str(user.id),
                "package_id": package["id"],
                "credits": str(package["credits"]),
            },
            description=f"Ogenti Credits: {package['label']}",
            # In test mode, auto-confirm with test card
            payment_method="pm_card_visa",
            confirm=True,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        )

        if intent.status == "succeeded":
            # Add credits
            old_tier = user.tier
            user.credits += package["credits"]

            # Auto-upgrade tier based on total credits
            if user.credits >= 50_000:
                user.tier = "enterprise"
            elif user.credits >= 5_000:
                user.tier = "pro"
            elif user.credits >= 1_000:
                user.tier = "starter"

            # Record transaction
            txn = Transaction(
                user_id=user.id,
                type="purchase",
                amount_cents=package["price_cents"],
                credits=package["credits"],
                description=f"Purchased {package['label']}",
                stripe_payment_id=intent.id,
            )
            db.add(txn)
            db.commit()

            return {
                "status": "success",
                "credits_added": package["credits"],
                "new_balance": user.credits,
                "tier_upgraded": user.tier != old_tier,
                "new_tier": user.tier,
                "payment_id": intent.id,
            }
        else:
            raise HTTPException(400, f"Payment not completed: {intent.status}")

    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {str(e)}")


@router.get("/balance")
async def get_balance(user: User = Depends(get_current_user)):
    """Get current credit balance"""
    tier_info = TIERS.get(user.tier, TIERS["free"])
    return {
        "credits": user.credits,
        "tier": user.tier,
        "tier_label": tier_info["label"],
    }


@router.get("/transactions")
async def get_transactions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get transaction history"""
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": t.id,
            "type": t.type,
            "amount_cents": t.amount_cents,
            "credits": t.credits,
            "description": t.description,
            "stripe_payment_id": t.stripe_payment_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in txns
    ]


@router.get("/stripe-key")
async def get_stripe_key():
    """Return publishable key for frontend"""
    return {"publishable_key": STRIPE_PUBLISHABLE_KEY}
