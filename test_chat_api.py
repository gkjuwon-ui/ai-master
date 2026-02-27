import urllib.request
import json

# Login
data = json.dumps({"email": "admin@ogenti.app", "password": "admin123456"}).encode()
req = urllib.request.Request("http://localhost:4000/api/auth/login", data=data, headers={"Content-Type": "application/json"})
try:
    resp = urllib.request.urlopen(req, timeout=5)
    result = json.loads(resp.read())
    token = result.get("token", "")
    print(f"Login OK, token: {token[:20]}...")
except Exception as e:
    print(f"Login failed: {e}")
    exit(1)

# Test owner-chat rooms endpoint
req2 = urllib.request.Request("http://localhost:4000/api/owner-chat/rooms", headers={"Authorization": f"Bearer {token}"})
try:
    resp2 = urllib.request.urlopen(req2, timeout=5)
    rooms = json.loads(resp2.read())
    print(f"Chat rooms: {json.dumps(rooms, indent=2)}")
except Exception as e:
    print(f"Rooms failed: {e}")

# Get first agent to test individual chat
req3 = urllib.request.Request("http://localhost:4000/api/agents?limit=1", headers={"Authorization": f"Bearer {token}"})
try:
    resp3 = urllib.request.urlopen(req3, timeout=5)
    agents = json.loads(resp3.read())
    if agents and isinstance(agents, list) and len(agents) > 0:
        agent_id = agents[0].get("id")
        print(f"\nFirst agent ID: {agent_id}, name: {agents[0].get('name')}")
    elif isinstance(agents, dict) and agents.get("agents"):
        agent_id = agents["agents"][0].get("id")
        print(f"\nFirst agent ID: {agent_id}")
    else:
        print(f"\nAgents response: {json.dumps(agents)[:200]}")
except Exception as e:
    print(f"Agents failed: {e}")
