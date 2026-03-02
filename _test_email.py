import httpx
resp = httpx.post(
    "https://api.resend.com/emails",
    headers={
        "Authorization": "Bearer re_jgpAsYJ2_CX7eMxTQzqb13U9Hu7cQZ3iP",
        "Content-Type": "application/json",
    },
    json={
        "from": "Ogenti <noreply@ogenti.com>",
        "to": ["gkjuwon@gmail.com"],
        "subject": "[OGENTI] Domain Verified - Test",
        "html": "<div style='font-family:Courier New;background:#0a0a1a;color:#00f0ff;padding:40px;text-align:center'><h1>DOMAIN VERIFIED</h1><p>noreply@ogenti.com is now active!</p></div>",
    },
)
print(resp.status_code, resp.text)
