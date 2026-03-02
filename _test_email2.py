import httpx
import sys
sys.path.insert(0, ".")
from ogenti_platform.email_service import generate_code

code = generate_code()
# Read the template from the module to test exact same HTML
html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Silkscreen:wght@400;700&display=swap');
</style>
</head>
<body style="margin:0;padding:0;background:#0a0a1a;">
<div style="background:#0a0a1a;padding:40px 16px;text-align:center;font-family:'Silkscreen','Press Start 2P','Courier New',monospace;">
    <div style="max-width:440px;margin:0 auto;background:#0f0f2a;border:2px solid #007088;box-shadow:inset -2px -2px 0 0 #00f0ff,inset 2px 2px 0 0 rgba(0,0,0,0.4);padding:0;">
        <!-- Header bar -->
        <div style="background:#12122a;border-bottom:2px solid #1a1a3a;padding:16px 20px;text-align:left;">
            <span style="font-family:'Press Start 2P','Courier New',monospace;font-size:9px;color:#6a6a8a;letter-spacing:2px;">SYSTEM://VERIFY</span>
        </div>
        <!-- Main content -->
        <div style="padding:32px 28px;">
            <h1 style="font-family:'Press Start 2P','Courier New',monospace;color:#00f0ff;font-size:18px;margin:0 0 6px 0;letter-spacing:3px;">&#9670; OGENTI &#9670;</h1>
            <p style="font-family:'Press Start 2P','Courier New',monospace;color:#3a3a5a;font-size:7px;margin:0 0 28px 0;letter-spacing:4px;">AI-TO-AI COMMUNICATION PROTOCOL</p>
            <p style="font-family:'Silkscreen','Courier New',monospace;color:#6a6a8a;font-size:12px;margin:0 0 16px 0;">Your verification code:</p>
            <!-- Code box -->
            <div style="background:#0a0a1a;border:2px solid #b060ff;box-shadow:inset -2px -2px 0 0 #b060ff,inset 2px 2px 0 0 rgba(0,0,0,0.5),0 0 20px rgba(176,96,255,0.15);padding:20px 16px;margin:0 0 20px 0;">
                <span style="font-family:'Press Start 2P','Courier New',monospace;font-size:32px;letter-spacing:10px;color:#00f0ff;">{code}</span>
            </div>
            <p style="font-family:'Silkscreen','Courier New',monospace;color:#3a3a5a;font-size:10px;margin:0;">Expires in 10 minutes</p>
        </div>
        <!-- Footer bar -->
        <div style="background:#12122a;border-top:2px solid #1a1a3a;padding:14px 20px;text-align:center;">
            <span style="font-family:'Press Start 2P','Courier New',monospace;font-size:7px;color:#2a2a4a;letter-spacing:3px;">PRESS START TO CONTINUE_</span>
        </div>
    </div>
    <!-- Bottom text -->
    <p style="font-family:'Silkscreen','Courier New',monospace;color:#2a2a4a;font-size:9px;margin-top:20px;letter-spacing:1px;">ogenti.com</p>
</div>
</body>
</html>
"""

resp = httpx.post(
    "https://api.resend.com/emails",
    headers={
        "Authorization": "Bearer re_jgpAsYJ2_CX7eMxTQzqb13U9Hu7cQZ3iP",
        "Content-Type": "application/json",
    },
    json={
        "from": "Ogenti <noreply@ogenti.com>",
        "to": ["gkjuwon@gmail.com"],
        "subject": f"[OGENTI] Verification Code: {code}",
        "html": html,
    },
)
print(resp.status_code, resp.text)
