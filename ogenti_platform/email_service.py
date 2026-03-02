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
            payload = {
                "from": f"Ogenti <{FROM_EMAIL}>",
                "to": [to_email],
                "subject": f"[OGENTI] Verification Code: {code}",
                "html": f"""
                    <div style="font-family:'Courier New',monospace;background:#0a0a1a;color:#c8c8e0;padding:40px;text-align:center;">
                        <div style="border:3px solid #00f0ff;padding:30px;max-width:420px;margin:0 auto;background:#0f0f2a;image-rendering:pixelated;">
                            <h1 style="font-family:'Courier New',monospace;color:#00f0ff;font-size:24px;margin-bottom:4px;letter-spacing:4px;text-shadow:0 0 10px rgba(0,240,255,0.4);">&#9670; OGENTI &#9670;</h1>
                            <p style="color:#6a6a8a;font-size:11px;margin-bottom:28px;letter-spacing:3px;">AI-TO-AI COMMUNICATION PROTOCOL</p>
                            <p style="color:#c8c8e0;font-size:13px;margin-bottom:8px;">Your verification code:</p>
                            <div style="background:#12122a;border:3px solid #b060ff;padding:20px;margin:16px 0;font-size:36px;letter-spacing:12px;color:#00f0ff;font-weight:bold;text-shadow:0 0 15px rgba(0,240,255,0.5);font-family:'Courier New',monospace;">
                                {code}
                            </div>
                            <p style="color:#6a6a8a;font-size:10px;margin-top:16px;">Expires in 10 minutes. Don't share this code.</p>
                            <div style="margin-top:28px;padding-top:16px;border-top:1px solid #1a1a3a;">
                                <span style="color:#3a3a5a;font-size:9px;letter-spacing:2px;">PRESS START TO CONTINUE_</span>
                            </div>
                        </div>
                    </div>
                    """,
            }
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code == 200:
                print(f"[EMAIL] Sent verification to {to_email}")
                return True
            else:
                print(f"[EMAIL] Resend API error {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        print(f"[EMAIL] Failed to send to {to_email}: {e}")
        return False


def get_code_expiry() -> datetime:
    """Get expiry time (10 minutes from now)"""
    return datetime.now(timezone.utc) + timedelta(minutes=10)
