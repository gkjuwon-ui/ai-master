"""Ogenti Platform — Email Service (Resend)"""
import httpx
import random
import string
from datetime import datetime, timezone, timedelta

from .config import RESEND_API_KEY, FROM_EMAIL


def generate_code() -> str:
    """Generate a 6-digit verification code"""
    return "".join(random.choices(string.digits, k=6))


def _build_email_html(code: str) -> str:
    """Build retro 8/16-bit styled verification email HTML.
    Mirrors the ogenti.com landing page design system:
    - Press Start 2P / Silkscreen pixel fonts
    - Pixel border with inset box-shadow (like .pixel-border-cyan)
    - Color palette: bg=#0a0a1a, surface=#0f0f2a, cyan=#00f0ff, purple=#b060ff
    - Retro card layout with header bar / content / footer bar
    """
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Silkscreen:wght@400;700&display=swap" rel="stylesheet">
</head><body style="margin:0;padding:0;background:#0a0a1a;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a1a;padding:48px 16px;">
<tr><td align="center">
<table width="440" cellpadding="0" cellspacing="0" style="background:#0f0f2a;border:4px solid #007088;box-shadow:inset -4px -4px 0 0 #00f0ff,inset 4px 4px 0 0 rgba(0,0,0,0.4);">
<!-- ▸ HEADER BAR -->
<tr><td style="background:#12122a;border-bottom:4px solid #1a1a3a;padding:14px 20px;">
<table width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="font-family:'Press Start 2P',monospace;font-size:8px;color:#3a3a5a;letter-spacing:3px;">SYSTEM://VERIFY</td>
<td align="right">
<span style="display:inline-block;width:8px;height:8px;background:#ff4060;margin-left:6px;"></span>
<span style="display:inline-block;width:8px;height:8px;background:#ffe040;margin-left:4px;"></span>
<span style="display:inline-block;width:8px;height:8px;background:#00ff88;margin-left:4px;"></span>
</td></tr></table>
</td></tr>
<!-- ▸ MAIN CONTENT -->
<tr><td style="padding:36px 32px;text-align:center;">
<!-- Logo -->
<table cellpadding="0" cellspacing="0" style="margin:0 auto 8px;"><tr>
<td style="font-family:'Press Start 2P',monospace;font-size:20px;color:#00f0ff;letter-spacing:4px;">&#9670; OGENTI &#9670;</td>
</tr></table>
<p style="font-family:'Press Start 2P',monospace;font-size:7px;color:#3a3a5a;letter-spacing:4px;margin:0 0 32px;">AI-TO-AI COMMUNICATION PROTOCOL</p>
<!-- Subtitle -->
<p style="font-family:'Silkscreen','Press Start 2P',monospace;font-size:12px;color:#6a6a8a;margin:0 0 16px;">ENTER THIS CODE TO VERIFY</p>
<!-- Code Box (pixel-border-purple) -->
<table cellpadding="0" cellspacing="0" style="margin:0 auto;">
<tr><td style="background:#0a0a1a;border:4px solid #b060ff;box-shadow:inset -4px -4px 0 0 #b060ff,inset 4px 4px 0 0 rgba(0,0,0,0.5);padding:24px 32px;">
<span style="font-family:'Press Start 2P',monospace;font-size:36px;letter-spacing:12px;color:#00f0ff;">{code}</span>
</td></tr></table>
<!-- Timer -->
<p style="font-family:'Press Start 2P',monospace;font-size:7px;color:#3a3a5a;margin:20px 0 0;letter-spacing:2px;">&#9201; EXPIRES IN 10 MIN</p>
</td></tr>
<!-- ▸ FOOTER BAR -->
<tr><td style="background:#12122a;border-top:4px solid #1a1a3a;padding:14px 20px;text-align:center;">
<span style="font-family:'Press Start 2P',monospace;font-size:7px;color:#2a2a4a;letter-spacing:3px;">PRESS START TO CONTINUE_</span>
</td></tr>
</table>
<!-- Bottom -->
<p style="font-family:'Press Start 2P',monospace;font-size:7px;color:#2a2a4a;margin-top:24px;letter-spacing:2px;">OGENTI.COM</p>
</td></tr></table>
</body></html>"""


async def send_verification_email(to_email: str, code: str) -> bool:
    """Send verification code via Resend API"""
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "from": f"Ogenti <{FROM_EMAIL}>",
                "to": [to_email],
                "subject": f"[OGENTI] Verification Code: {code}",
                "html": _build_email_html(code),
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
