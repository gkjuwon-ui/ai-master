import urllib.request
import json

# Login
data = json.dumps({"email": "admin@ogenti.app", "password": "admin123456"}).encode()
req = urllib.request.Request("http://localhost:4000/api/auth/login", data=data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=5)
result = json.loads(resp.read())
print(f"Login response keys: {list(result.keys())}")

# Navigate to find the token
if 'token' in result:
    token = result['token']
elif 'data' in result and isinstance(result['data'], dict):
    token = result['data'].get('token', result['data'].get('accessToken', ''))
    if not token:
        print(f"Data keys: {list(result['data'].keys())}")
        print(f"Data: {json.dumps(result['data'])[:500]}")
        exit(1)
    token = result['accessToken']
else:
    print(f"Full response: {json.dumps(result)[:500]}")
    exit(1)

print(f"Token: {token[:30]}..." if token else "No token found!")

# Test owner-chat
auth_header = f"Bearer {token}"
print(f"Auth header: {auth_header[:40]}...")

req2 = urllib.request.Request("http://localhost:4000/api/owner-chat/rooms", headers={"Authorization": auth_header})
try:
    resp2 = urllib.request.urlopen(req2, timeout=5)
    print(f"Rooms: {resp2.read().decode()[:300]}")
except urllib.error.HTTPError as e:
    print(f"Rooms error {e.code}: {e.read().decode()[:300]}")
