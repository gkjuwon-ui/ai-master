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


def _ensure_stripe_key():
    """Set Stripe API key fresh from env every time (avoids stale module-level value)."""
    import os
    key = os.getenv("STRIPE_SECRET_KEY", STRIPE_SECRET_KEY)
    stripe.api_key = key
    return key


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
    """Create Stripe Checkout Session — redirects user to real payment page."""

    # Find package
    package = next((p for p in CREDIT_PACKAGES if p["id"] == req.package_id), None)
    if not package:
        raise HTTPException(400, "Invalid package")

    try:
        _ensure_stripe_key()

        # Create Stripe Checkout Session (shows actual card form)
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": package["price_cents"],
                    "product_data": {
                        "name": f"Ogenti {package['label']}",
                        "description": f"{package['credits']:,} credits for AI adapter training & inference",
                    },
                },
                "quantity": 1,
            }],
            metadata={
                "user_id": str(user.id),
                "package_id": package["id"],
                "credits": str(package["credits"]),
            },
            success_url="https://ogenti.com/platform/billing.html?payment=success",
            cancel_url="https://ogenti.com/platform/billing.html?payment=cancelled",
        )

        return {
            "status": "checkout",
            "checkout_url": session.url,
            "session_id": session.id,
        }

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
    import os
    return {"publishable_key": os.getenv("STRIPE_PUBLISHABLE_KEY", STRIPE_PUBLISHABLE_KEY)}


@router.get("/debug-key")
async def debug_stripe_key():
    """Show masked Stripe key for debugging (never exposes full key)."""
    import os
    sk = os.getenv("STRIPE_SECRET_KEY", "NOT_SET")
    pk = os.getenv("STRIPE_PUBLISHABLE_KEY", "NOT_SET")
    wh = os.getenv("STRIPE_WEBHOOK_SECRET", "NOT_SET")
    mask = lambda k: k[:12] + "****" + k[-4:] if len(k) > 16 else k
    return {
        "secret_key": mask(sk),
        "publishable_key": mask(pk),
        "webhook_secret": mask(wh),
        "stripe_lib_key": mask(stripe.api_key) if stripe.api_key else "NOT_SET",
    }


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook — handles checkout.session.completed to add credits."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        _ensure_stripe_key()
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")

    # Checkout Session completed — user paid through Stripe's card form
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata", {})
        user_id = int(meta.get("user_id", 0))
        credits = int(meta.get("credits", 0))
        package_id = meta.get("package_id", "")
        payment_id = session.get("payment_intent") or session.get("id")

        if user_id and credits:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                # 중복 처리 방지
                existing = db.query(Transaction).filter(
                    Transaction.stripe_payment_id == payment_id
                ).first()
                if not existing:
                    user.credits += credits
                    if user.credits >= 50_000:
                        user.tier = "enterprise"
                    elif user.credits >= 5_000:
                        user.tier = "pro"
                    elif user.credits >= 1_000:
                        user.tier = "starter"

                    txn = Transaction(
                        user_id=user.id,
                        type="purchase",
                        amount_cents=session.get("amount_total", 0),
                        credits=credits,
                        description=f"Purchased {package_id} package",
                        stripe_payment_id=payment_id,
                    )
                    db.add(txn)
                    db.commit()

    return {"status": "ok"}
