import httpx
resp = httpx.get(
    "https://api.resend.com/domains/4d4e3e14-b3ba-480e-9d1a-c9edfc66f559",
    headers={"Authorization": "Bearer re_jgpAsYJ2_CX7eMxTQzqb13U9Hu7cQZ3iP"},
)
data = resp.json()
print("Domain Status:", data.get("status"))
for r in data.get("records", []):
    print(f"  {r['record']} ({r['name']}): {r['status']}")
