import urllib.request
import json

# Login
data = json.dumps({"email": "admin@ogenti.app", "password": "admin123456"}).encode()
req = urllib.request.Request("http://localhost:4000/api/auth/login", data=data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=5)
result = json.loads(resp.read())
token = result['data']['tokens']['accessToken']
print(f"Token OK: {token[:30]}...")

# Test owner-chat rooms
req2 = urllib.request.Request("http://localhost:4000/api/owner-chat/rooms", headers={"Authorization": f"Bearer {token}"})
try:
    resp2 = urllib.request.urlopen(req2, timeout=5)
    rooms_data = json.loads(resp2.read())
    print(f"Rooms: {json.dumps(rooms_data, indent=2)[:300]}")
except urllib.error.HTTPError as e:
    print(f"Rooms error {e.code}: {e.read().decode()[:300]}")

# Test creating individual chat with first agent
req3 = urllib.request.Request("http://localhost:4000/api/agents?limit=1", headers={"Authorization": f"Bearer {token}"})
try:
    resp3 = urllib.request.urlopen(req3, timeout=5)
    agents_result = json.loads(resp3.read())
    agents = agents_result.get('data', {}).get('agents', [])
    if agents:
        agent_id = agents[0]['id']
        agent_name = agents[0].get('name', 'Unknown')
        print(f"\nCreating chat with agent: {agent_name} ({agent_id})")
        
        body = json.dumps({"agentProfileId": agent_id}).encode()
        req4 = urllib.request.Request(
            "http://localhost:4000/api/owner-chat/rooms/individual",
            data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        resp4 = urllib.request.urlopen(req4, timeout=10)
        chat = json.loads(resp4.read())
        print(f"Chat created: {json.dumps(chat, indent=2)[:400]}")
except urllib.error.HTTPError as e:
    print(f"Error {e.code}: {e.read().decode()[:300]}")
except Exception as e:
    print(f"Error: {e}")
