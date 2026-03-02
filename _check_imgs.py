import httpx

imgs = ["logo", "d0", "d5", "header", "dots", "subtitle", "verify_text", "footer"]
for n in imgs:
    url = f"https://ogenti.com/email/{n}.png"
    r = httpx.get(url, timeout=10, follow_redirects=True)
    print(f"{n}.png: {r.status_code} ({len(r.content)} bytes)")
