"""OGENTI API Endpoint Verification"""
import requests
import json

BASE = "http://localhost:8000"

print("=" * 60)
print("  OGENTI API ENDPOINT VERIFICATION")
print("=" * 60)

endpoints = [
    ("GET", "/api/status",   "Server status"),
    ("GET", "/api/metrics",  "Training metrics"),
    ("GET", "/api/phases",   "Phase config"),
    ("GET", "/api/channel",  "Channel stats"),
    ("GET", "/api/vocab",    "Vocabulary"),
    ("GET", "/api/snapshot", "Full snapshot"),
]

all_pass = True

for method, path, desc in endpoints:
    try:
        r = requests.get(f"{BASE}{path}", timeout=3)
        data = r.json()
        if isinstance(data, dict):
            keys = list(data.keys())[:5]
        else:
            keys = f"[list: {len(data)} items]"
        ok = r.status_code == 200
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{tag}] {desc:<20s} {path:<20s} -> {r.status_code}  keys={keys}")
    except Exception as e:
        all_pass = False
        print(f"  [FAIL] {desc:<20s} {path:<20s} -> {e}")

# Pause / Resume
for action in ["pause", "resume"]:
    try:
        r = requests.post(f"{BASE}/api/training/{action}", timeout=3)
        ok = r.status_code == 200
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{tag}] {action:<20s} /api/training/{action:<8s} -> {r.status_code}")
    except Exception as e:
        all_pass = False
        print(f"  [FAIL] {action:<20s} -> {e}")

# Dashboard HTML
r = requests.get(f"{BASE}/", timeout=3)
has_ogenti = "OGENTI" in r.text
has_canvas = "agentCanvas" in r.text
has_badge = "connectionBadge" in r.text
html_ok = has_ogenti and has_canvas and has_badge
tag = "PASS" if html_ok else "FAIL"
if not html_ok:
    all_pass = False
print(f"  [{tag}] Dashboard HTML       /                    -> {r.status_code}  OGENTI={has_ogenti} canvas={has_canvas} badge={has_badge}")

# Deep inspection: /api/status
print()
print("-" * 60)
print("  DEEP INSPECT: /api/status")
print("-" * 60)
r = requests.get(f"{BASE}/api/status", timeout=3)
status = r.json()
for k, v in status.items():
    print(f"    {k:<16s} = {v}")

# Deep inspection: /api/snapshot
print()
print("-" * 60)
print("  DEEP INSPECT: /api/snapshot (key structure)")
print("-" * 60)
r = requests.get(f"{BASE}/api/snapshot", timeout=3)
snap = r.json()
for k, v in snap.items():
    if isinstance(v, list):
        print(f"    {k:<16s} = [{len(v)} items]")
    elif isinstance(v, dict):
        print(f"    {k:<16s} = dict({list(v.keys())})")
    else:
        print(f"    {k:<16s} = {v}")

# Metrics history check
print()
print("-" * 60)
print("  DEEP INSPECT: /api/metrics (last 3 entries)")
print("-" * 60)
r = requests.get(f"{BASE}/api/metrics", timeout=3)
data = r.json()
history = data.get("history", [])
print(f"    Total history entries: {len(history)}")
for entry in history[-3:]:
    ep = entry.get("episode", "?")
    comp = entry.get("compression", "?")
    fid = entry.get("fidelity", "?")
    bud = entry.get("budget", "?")
    print(f"    ep={ep:<6}  compression={comp:<8}  fidelity={fid:<8}  budget={bud}")

# Vocab check
print()
print("-" * 60)
print("  DEEP INSPECT: /api/vocab")
print("-" * 60)
r = requests.get(f"{BASE}/api/vocab", timeout=3)
data = r.json()
vocab = data.get("tokens", [])
print(f"    Discovered tokens: {len(vocab)}")
for t in vocab[:5]:
    print(f"    id={t.get('id','?'):<5} meaning={t.get('meaning','?'):<16} cat={t.get('category','?')}")

print()
print("=" * 60)
if all_pass:
    print("  ALL TESTS PASSED")
else:
    print("  SOME TESTS FAILED")
print("=" * 60)
