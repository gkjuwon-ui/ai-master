"""OGENTI WebSocket Streaming Verification"""
import asyncio
import websockets
import json
import time
from collections import Counter

async def verify_websocket():
    print("=" * 60)
    print("  OGENTI WEBSOCKET STREAMING VERIFICATION")
    print("=" * 60)
    print()

    uri = "ws://localhost:8000/ws"
    event_types = Counter()
    events = []
    phases_seen = set()
    vocab_seen = []
    channel_msgs = []
    episodes = []

    print(f"  Connecting to {uri} ...")
    
    async with websockets.connect(uri) as ws:
        print("  Connected! Collecting events for ~8 seconds...")
        print()

        start = time.time()
        
        while time.time() - start < 8:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
                msg = json.loads(raw)
                t = msg.get("type", "unknown")
                d = msg.get("data", {})
                event_types[t] += 1
                events.append(msg)

                if t == "state":
                    print(f"    [state]     Full snapshot: ep={d.get('episode')} phase={d.get('phase')} "
                          f"compression={d.get('compression')} fidelity={d.get('fidelity')}")
                    
                elif t == "episode":
                    ep = d.get("episode", 0)
                    episodes.append(ep)
                    if len(episodes) <= 3 or len(episodes) % 10 == 0:
                        print(f"    [episode]   ep={ep:<6} compression={d.get('compression','?'):<8} "
                              f"fidelity={d.get('fidelity','?'):<8} tokens={d.get('tokens','?')} "
                              f"budget={d.get('budget','?')}")
                    
                elif t == "phase":
                    phases_seen.add(d.get("name", "?"))
                    print(f"    [phase]     Phase transition -> {d.get('name')} (phase {d.get('phase')})")
                    
                elif t == "channel":
                    channel_msgs.append(d)
                    if len(channel_msgs) <= 3:
                        sender = d.get("sender", "?")
                        receiver = d.get("receiver", "?")
                        tc = d.get("token_count", "?")
                        ok = d.get("success", "?")
                        print(f"    [channel]   {sender} -> {receiver}  tokens={tc}  success={ok}")
                    
                elif t == "vocab":
                    vocab_seen.append(d)
                    print(f"    [vocab]     Discovered: id={d.get('id')} meaning={d.get('meaning')} cat={d.get('category')}")
                    
                elif t == "heartbeat":
                    pass  # silent
                    
            except asyncio.TimeoutError:
                continue

        # Send ping command and check pong
        print()
        print("  Testing WebSocket commands...")
        
        async def wait_for_type(ws, expected_type, timeout=3):
            """Wait for a specific event type, skipping broadcast events."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.time())
                    msg = json.loads(raw)
                    if msg.get("type") == expected_type:
                        return msg
                except asyncio.TimeoutError:
                    break
            return None
        
        await ws.send(json.dumps({"cmd": "ping"}))
        pong = await wait_for_type(ws, "pong")
        pong_ok = pong is not None
        ts_val = pong.get("data", {}).get("ts", "?") if pong else "?"
        print(f"    [{'PASS' if pong_ok else 'FAIL'}] ping -> pong  (ts={ts_val})")

        # Send snapshot command
        await ws.send(json.dumps({"cmd": "snapshot"}))
        snap_msg = await wait_for_type(ws, "state")
        snap_ok = snap_msg is not None and "episode" in snap_msg.get("data", {})
        snap_data = snap_msg.get("data", {}) if snap_msg else {}
        print(f"    [{'PASS' if snap_ok else 'FAIL'}] snapshot -> state  "
              f"(ep={snap_data.get('episode')} keys={len(snap_data)})")

        # Send pause command
        await ws.send(json.dumps({"cmd": "pause"}))
        pause_msg = await wait_for_type(ws, "status")
        pause_ok = pause_msg is not None and pause_msg.get("data", {}).get("status") == "paused"
        pause_status = pause_msg.get("data", {}).get("status", "?") if pause_msg else "?"
        print(f"    [{'PASS' if pause_ok else 'FAIL'}] pause   -> status={pause_status}")

        # Send resume command
        await ws.send(json.dumps({"cmd": "resume"}))
        resume_msg = await wait_for_type(ws, "status")
        resume_ok = resume_msg is not None and resume_msg.get("data", {}).get("status") == "training"
        resume_status = resume_msg.get("data", {}).get("status", "?") if resume_msg else "?"
        print(f"    [{'PASS' if resume_ok else 'FAIL'}] resume  -> status={resume_status}")

    # Summary
    print()
    print("=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    print()
    print(f"    Total events received:    {len(events)}")
    print(f"    Event type breakdown:")
    for t, c in event_types.most_common():
        print(f"      {t:<16s}  {c:>4d}")
    print()
    
    if episodes:
        print(f"    Episodes tracked:         {len(episodes)}")
        print(f"    Episode range:            {min(episodes)} -> {max(episodes)}")
        ep_rate = (max(episodes) - min(episodes)) / 8 if len(episodes) > 1 else 0
        print(f"    Effective ep/s:           ~{ep_rate:.1f}")
    
    print(f"    Channel messages:         {len(channel_msgs)}")
    print(f"    Vocab discovered:         {len(vocab_seen)}")
    print()
    
    # Verification checks
    checks = [
        ("Initial state snapshot",    event_types.get("state", 0) >= 1),
        ("Episode events flowing",    event_types.get("episode", 0) >= 5),
        ("Channel events flowing",    event_types.get("channel", 0) >= 1),
        ("Episodes incrementing",     len(episodes) >= 2 and episodes[-1] > episodes[0]),
        ("Ping/pong works",           pong_ok),
        ("Snapshot command works",    snap_ok),
        ("Pause command works",       pause_ok),
        ("Resume command works",      resume_ok),
    ]
    
    all_pass = True
    for name, ok in checks:
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"    [{tag}] {name}")
    
    print()
    print("=" * 60)
    if all_pass:
        print("  ALL WEBSOCKET TESTS PASSED")
    else:
        print("  SOME TESTS FAILED")
    print("=" * 60)

asyncio.run(verify_websocket())
