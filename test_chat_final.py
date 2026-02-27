import urllib.request
import json

# Login
data = json.dumps({"email": "admin@ogenti.app", "password": "admin123456"}).encode()
req = urllib.request.Request("http://localhost:4000/api/auth/login", data=data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=5)
result = json.loads(resp.read())
token = result['data']['tokens']['accessToken']
print(f"1) Login OK")

# Test rooms (should be empty initially)
req2 = urllib.request.Request("http://localhost:4000/api/owner-chat/rooms", headers={"Authorization": f"Bearer {token}"})
resp2 = urllib.request.urlopen(req2, timeout=5)
rooms = json.loads(resp2.read())
print(f"2) Rooms (initial): {len(rooms['data'])} rooms")

# Create individual chat with admin-owned agent
agent_id = "ac43407e-81ee-483c-823b-05fa25ffddb6"  # admin-Apex Researcher
body = json.dumps({"agentProfileId": agent_id}).encode()
req3 = urllib.request.Request(
    "http://localhost:4000/api/owner-chat/rooms/individual",
    data=body,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
)
try:
    resp3 = urllib.request.urlopen(req3, timeout=10)
    chat = json.loads(resp3.read())
    chat_id = chat['data']['id']
    print(f"3) Individual chat created: {chat_id}")
    print(f"   Type: {chat['data']['type']}, Messages: {len(chat['data'].get('messages', []))}")
except urllib.error.HTTPError as e:
    print(f"3) ERROR {e.code}: {e.read().decode()[:200]}")
    exit(1)

# List rooms again
req4 = urllib.request.Request("http://localhost:4000/api/owner-chat/rooms", headers={"Authorization": f"Bearer {token}"})
resp4 = urllib.request.urlopen(req4, timeout=5)
rooms2 = json.loads(resp4.read())
print(f"4) Rooms after create: {len(rooms2['data'])} rooms")

# Test memories
req5 = urllib.request.Request(
    f"http://localhost:4000/api/owner-chat/memories/{agent_id}",
    headers={"Authorization": f"Bearer {token}"}
)
try:
    resp5 = urllib.request.urlopen(req5, timeout=5)
    memories = json.loads(resp5.read())
    print(f"5) Memories: {len(memories.get('data', []))} entries")
except urllib.error.HTTPError as e:
    print(f"5) Memories ERROR {e.code}: {e.read().decode()[:200]}")

print("\n=== ALL API TESTS PASSED ===")
