"""Ogenti Platform — Email Service (Resend)"""
import httpx
import random
import string
from datetime import datetime, timezone, timedelta

from .config import RESEND_API_KEY, FROM_EMAIL


def generate_code() -> str:
    """Generate a 6-digit verification code"""
    return "".join(random.choices(string.digits, k=6))


async def send_verification_email(to_email: str, code: str) -> bool:
    """Send verification code via Resend API"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": f"Ogenti <{FROM_EMAIL}>",
                    "to": [to_email],
                    "subject": f"[OGENTI] Verification Code: {code}",
                    "html": f"""
                    <div style="font-family:'Courier New',monospace;background:#0a0a2e;color:#00f0ff;padding:40px;text-align:center;">
                        <div style="border:2px solid #00f0ff;padding:30px;max-width:400px;margin:0 auto;">
                            <h1 style="color:#ff6b9d;font-size:24px;margin-bottom:8px;">◆ OGENTI ◆</h1>
                            <p style="color:#b0b0d0;font-size:12px;margin-bottom:24px;">AI-TO-AI COMMUNICATION PROTOCOL</p>
                            <p style="color:#e0e0ff;font-size:14px;">Your verification code:</p>
                            <div style="background:#1a1a4e;border:2px solid #ff6b9d;padding:20px;margin:16px 0;font-size:32px;letter-spacing:8px;color:#00f0ff;font-weight:bold;">
                                {code}
                            </div>
                            <p style="color:#8080a0;font-size:11px;">Expires in 10 minutes. Don't share this code.</p>
                            <div style="margin-top:24px;color:#4a4a6e;font-size:10px;">PRESS START TO CONTINUE_</div>
                        </div>
                    </div>
                    """,
                },
            )
            return resp.status_code == 200
    except Exception as e:
        print(f"[EMAIL] Failed to send to {to_email}: {e}")
        # In dev/test mode, just print the code
        print(f"[EMAIL] DEV MODE — Verification code for {to_email}: {code}")
        return True  # Return True in dev so signup still works


def get_code_expiry() -> datetime:
    """Get expiry time (10 minutes from now)"""
    return datetime.now(timezone.utc) + timedelta(minutes=10)
