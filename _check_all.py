"""Check all 3 issues: domain status, email delivery, deployed billing"""
import httpx
import json

API_KEY = "re_jgpAsYJ2_CX7eMxTQzqb13U9Hu7cQZ3iP"
DOMAIN_ID = "4d4e3e14-b3ba-480e-9d1a-c9edfc66f559"

# 1. Check Resend domain status
print("=" * 50)
print("1. RESEND DOMAIN STATUS")
print("=" * 50)
r = httpx.get(
    f"https://api.resend.com/domains/{DOMAIN_ID}",
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=10,
)
d = r.json()
print(f"Domain: {d.get('name')}")
print(f"Status: {d.get('status')}")
print(f"Region: {d.get('region')}")
for rec in d.get("records", []):
    print(f"  {rec.get('record_type')} {rec.get('name')}: {rec.get('status')}")

# 2. Test send to a non-gmail address
print("\n" + "=" * 50)
print("2. TEST SEND TO ceo@ogenti.com")
print("=" * 50)
r2 = httpx.post(
    "https://api.resend.com/emails",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "from": "Ogenti <noreply@ogenti.com>",
        "to": ["ceo@ogenti.com"],
        "subject": "Test delivery",
        "html": "<p>Test</p>",
    },
    timeout=10,
)
print(f"Status: {r2.status_code}")
print(f"Response: {r2.text}")

# 3. Check Resend API key info (account type)
print("\n" + "=" * 50)
print("3. RESEND API KEYS / ACCOUNT INFO")
print("=" * 50)
r3 = httpx.get(
    "https://api.resend.com/api-keys",
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=10,
)
print(f"API Keys: {r3.status_code} {r3.text[:300]}")

# 4. Check recent emails sent
print("\n" + "=" * 50)
print("4. RECENT EMAILS")
print("=" * 50)
r4 = httpx.get(
    "https://api.resend.com/emails",
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=10,
)
print(f"Emails: {r4.status_code} {r4.text[:500]}")
