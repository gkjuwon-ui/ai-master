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
    Uses pre-rendered PNG images with Press Start 2P font so it works
    in ALL email clients including Outlook (which blocks web fonts).
    Images hosted on ogenti.com/email/
    """
    IMG = "https://ogenti.com/email"
    # Build digit images for the 6-digit code
    digits_html = "".join(
        f'<img src="{IMG}/d{d}.png" alt="{d}" '
        f'style="display:inline-block;height:54px;margin:0 2px;" />'
        for d in code
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0a1a;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a1a;padding:48px 16px;">
<tr><td align="center">
<table width="440" cellpadding="0" cellspacing="0" style="background:#0f0f2a;border:4px solid #007088;box-shadow:inset -4px -4px 0 0 #00f0ff,inset 4px 4px 0 0 rgba(0,0,0,0.4);">
<!-- HEADER BAR -->
<tr><td style="background:#12122a;border-bottom:4px solid #1a1a3a;padding:14px 20px;">
<table width="100%" cellpadding="0" cellspacing="0"><tr>
<td><img src="{IMG}/header.png" alt="SYSTEM://VERIFY" style="height:14px;" /></td>
<td align="right"><img src="{IMG}/dots.png" alt="..." style="height:16px;" /></td>
</tr></table>
</td></tr>
<!-- MAIN CONTENT -->
<tr><td style="padding:36px 32px;text-align:center;">
<img src="{IMG}/logo.png" alt="OGENTI" style="height:40px;margin-bottom:8px;" /><br/>
<img src="{IMG}/subtitle.png" alt="AI-TO-AI COMMUNICATION PROTOCOL" style="height:14px;margin-bottom:32px;" /><br/>
<img src="{IMG}/verify_text.png" alt="ENTER THIS CODE TO VERIFY" style="height:18px;margin-bottom:20px;" /><br/>
<!-- CODE BOX -->
<table cellpadding="0" cellspacing="0" style="margin:0 auto;">
<tr><td style="background:#0a0a1a;border:4px solid #b060ff;box-shadow:inset -4px -4px 0 0 #b060ff,inset 4px 4px 0 0 rgba(0,0,0,0.5);padding:16px 24px;text-align:center;">
{digits_html}
</td></tr></table>
<br/>
<img src="{IMG}/expires.png" alt="EXPIRES IN 10 MIN" style="height:14px;margin-top:16px;" />
</td></tr>
<!-- FOOTER BAR -->
<tr><td style="background:#12122a;border-top:4px solid #1a1a3a;padding:14px 20px;text-align:center;">
<img src="{IMG}/footer.png" alt="PRESS START TO CONTINUE_" style="height:14px;" />
</td></tr>
</table>
<br/>
<img src="{IMG}/bottom.png" alt="OGENTI.COM" style="height:14px;margin-top:16px;" />
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
