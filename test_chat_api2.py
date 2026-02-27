import urllib.request
import json

# Login
data = json.dumps({"email": "admin@ogenti.app", "password": "admin123456"}).encode()
req = urllib.request.Request("http://localhost:4000/api/auth/login", data=data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=5)
result = json.loads(resp.read())
token = result.get("token", "")
print(f"Login OK, token starts: {token[:20]}...")

# Test various paths
paths = [
    ("GET", "/api/owner-chat/rooms", None),
    ("GET", "/api/election/status", None),
    ("GET", "/api/social/friends", None),
]

for method, path, body_data in paths:
    url = f"http://localhost:4000{path}"
    try:
        req2 = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        if method == "POST" and body_data:
            req2.data = json.dumps(body_data).encode()
            req2.add_header("Content-Type", "application/json")
        resp2 = urllib.request.urlopen(req2, timeout=5)
        data = resp2.read().decode()[:200]
        print(f"  {method} {path} => {resp2.status}: {data}")
    except urllib.error.HTTPError as e:
        print(f"  {method} {path} => {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        print(f"  {method} {path} => ERROR: {e}")
