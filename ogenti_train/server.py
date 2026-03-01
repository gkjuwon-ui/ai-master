"""
OGENTI Protocol Monitor — API Server

FastAPI + WebSocket server that bridges the training loop to the frontend dashboard.

Modes:
  1. **Live mode**: Attached to a running OgentiTrainer via TrainerBridge
  2. **Standalone mode**: Runs independently, serves dashboard + REST API for stored metrics

Usage:
  # Standalone (just dashboard):
  python -m ogenti_train.server

  # From training script:
  from ogenti_train.server import TrainerBridge, start_server
  bridge = TrainerBridge()
  # ... attach to trainer, then:
  start_server(bridge, host="0.0.0.0", port=8000)

WebSocket Events (server → client):
  {"type": "episode",    "data": { episode metrics dict }}
  {"type": "phase",      "data": { phase transition info }}
  {"type": "channel",    "data": { channel stats summary }}
  {"type": "vocab",      "data": { discovered token info }}
  {"type": "eval",       "data": { evaluation results }}
  {"type": "state",      "data": { full snapshot for late-joiners }}
  {"type": "status",     "data": { server status }}

REST Endpoints:
  GET  /api/status          — server + training status
  GET  /api/metrics          — recent metrics history
  GET  /api/phases           — phase config + history
  GET  /api/channel          — channel statistics
  GET  /api/vocab            — discovered vocabulary
  GET  /api/snapshot         — full state snapshot
  POST /api/training/pause   — pause training
  POST /api/training/resume  — resume training

"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# Trainer Bridge — connects training loop to WebSocket broadcast
# ────────────────────────────────────────────────────────────────

@dataclass
class VocabToken:
    """A discovered emergent protocol token."""
    token_id: int
    meaning: str
    category: str
    frequency: int = 0
    phase_discovered: int = 0
    episode_discovered: int = 0


@dataclass
class TrainerBridge:
    """
    Thread-safe bridge between OgentiTrainer and the WebSocket server.
    
    The trainer calls on_episode(), on_phase_change(), etc. from its thread.
    The server reads from the shared state via asyncio-safe methods.
    """
    # Current state
    status: str = "idle"  # idle, training, paused, completed
    episode: int = 0
    phase: int = 0
    phase_name: str = "warmup"
    start_time: float = field(default_factory=time.time)
    
    # Metrics
    compression: float = 1.0
    fidelity: float = 0.0
    avg_tokens: int = 30
    budget: float = 30.0
    total_reward: float = 0.0
    efficiency: float = 0.0
    
    # History (rolling window)
    metrics_history: deque = field(default_factory=lambda: deque(maxlen=500))
    episode_log: deque = field(default_factory=lambda: deque(maxlen=100))
    
    # Phase tracking
    phase_configs: list[dict] = field(default_factory=list)
    phase_history: list[dict] = field(default_factory=list)
    current_phase_metrics: dict = field(default_factory=dict)
    
    # Channel stats
    channel_stats: dict = field(default_factory=lambda: {
        "messages_sent": 0,
        "messages_dropped": 0,
        "drop_rate": 0.0,
        "total_tokens": 0,
        "compression_ratio": 1.0,
        "noise_injections": 0,
        "relay_hops": 0,
    })
    
    # Vocabulary
    vocab: list[VocabToken] = field(default_factory=list)
    vocab_freq: dict[int, int] = field(default_factory=dict)
    
    # Eval results
    last_eval: dict = field(default_factory=dict)
    
    # Event queue for WebSocket broadcast
    _event_queue: deque = field(default_factory=lambda: deque(maxlen=200))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    # ── Trainer callbacks ──────────────────────────────────────
    
    def on_training_start(self, config: dict | None = None) -> None:
        """Called when training begins."""
        with self._lock:
            self.status = "training"
            self.start_time = time.time()
            if config:
                self.phase_configs = config.get("phases", [])
            self._push_event("status", {
                "status": "training",
                "start_time": self.start_time,
            })
    
    def on_episode(self, metrics: dict) -> None:
        """Called after each training episode with its metrics dict."""
        with self._lock:
            self.episode = metrics.get("episode", self.episode + 1)
            self.phase = metrics.get("phase", self.phase)
            self.compression = metrics.get("compression_ratio", self.compression)
            self.fidelity = metrics.get("accuracy", self.fidelity)
            self.avg_tokens = metrics.get("protocol_tokens", self.avg_tokens)
            self.total_reward = metrics.get("total_reward", self.total_reward)
            self.efficiency = metrics.get("efficiency", self.efficiency)
            
            # Compute budget from config if available
            if "budget" in metrics:
                self.budget = metrics["budget"]
            
            # Track token frequencies for vocab discovery
            if "token_ids" in metrics:
                for tid in metrics["token_ids"]:
                    self.vocab_freq[tid] = self.vocab_freq.get(tid, 0) + 1
            
            # Rolling history
            entry = {
                "episode": self.episode,
                "compression": self.compression,
                "fidelity": self.fidelity * 100,
                "budget": self.budget,
                "reward": self.total_reward,
                "tokens": self.avg_tokens,
                "phase": self.phase,
                "timestamp": time.time(),
            }
            self.metrics_history.append(entry)
            self.episode_log.append(metrics)
            
            self._push_event("episode", entry)
    
    def on_message(self, message_data: dict) -> None:
        """Called when a protocol message is sent through the channel."""
        with self._lock:
            cs = self.channel_stats
            cs["messages_sent"] = message_data.get("messages_sent", cs["messages_sent"])
            cs["messages_dropped"] = message_data.get("messages_dropped", cs["messages_dropped"])
            cs["total_tokens"] = message_data.get("total_tokens", cs["total_tokens"])
            cs["compression_ratio"] = message_data.get("compression_ratio", cs["compression_ratio"])
            cs["noise_injections"] = message_data.get("noise_injections", cs["noise_injections"])
            cs["relay_hops"] = message_data.get("relay_hops", cs["relay_hops"])
            total = cs["messages_sent"] + cs["messages_dropped"]
            cs["drop_rate"] = cs["messages_dropped"] / total if total > 0 else 0.0
            
            self._push_event("channel", {
                **cs,
                "sender": message_data.get("sender_id", ""),
                "receiver": message_data.get("receiver_id", ""),
                "token_ids": message_data.get("token_ids", []),
                "token_count": message_data.get("token_count", 0),
                "message_type": message_data.get("message_type", ""),
                "success": message_data.get("success", True),
                "fidelity": message_data.get("fidelity", 0.0),
                "task": message_data.get("task", ""),
            })
    
    def on_phase_change(self, phase_data: dict) -> None:
        """Called when curriculum phase advances."""
        with self._lock:
            self.phase = phase_data.get("new_phase", self.phase)
            self.phase_name = phase_data.get("new_phase_name", self.phase_name)
            if "completed_phase_summary" in phase_data:
                self.phase_history.append(phase_data["completed_phase_summary"])
            self.current_phase_metrics = phase_data.get("current_metrics", {})
            
            self._push_event("phase", {
                "phase": self.phase,
                "name": self.phase_name,
                "history": self.phase_history,
                "current_metrics": self.current_phase_metrics,
            })
    
    def on_vocab_discovered(self, token: dict) -> None:
        """Called when a new emergent token pattern is detected."""
        with self._lock:
            vt = VocabToken(
                token_id=token.get("token_id", 0),
                meaning=token.get("meaning", "unknown"),
                category=token.get("category", "unknown"),
                frequency=token.get("frequency", 0),
                phase_discovered=self.phase,
                episode_discovered=self.episode,
            )
            self.vocab.append(vt)
            self._push_event("vocab", {
                "id": vt.token_id,
                "meaning": vt.meaning,
                "category": vt.category,
                "freq": vt.frequency,
                "phase": vt.phase_discovered,
            })
    
    def on_eval(self, eval_data: dict) -> None:
        """Called after evaluation run."""
        with self._lock:
            self.last_eval = eval_data
            self._push_event("eval", eval_data)
    
    def on_training_end(self, summary: dict | None = None) -> None:
        """Called when training finishes."""
        with self._lock:
            self.status = "completed"
            self._push_event("status", {
                "status": "completed",
                "summary": summary or {},
            })

    def on_adapter_exported(self, export_info: dict) -> None:
        """Called when Phase 4 completes and the universal adapter is exported."""
        with self._lock:
            self._push_event("adapter_exported", export_info)
    
    def pause(self) -> None:
        with self._lock:
            self.status = "paused"
            self._push_event("status", {"status": "paused"})
    
    def resume(self) -> None:
        with self._lock:
            self.status = "training"
            self._push_event("status", {"status": "training"})
    
    # ── Snapshot for late-joining clients ──────────────────────
    
    def snapshot(self) -> dict:
        """Full state snapshot for newly connected clients."""
        with self._lock:
            return {
                "status": self.status,
                "episode": self.episode,
                "phase": self.phase,
                "phase_name": self.phase_name,
                "compression": self.compression,
                "fidelity": self.fidelity,
                "avg_tokens": self.avg_tokens,
                "budget": self.budget,
                "total_reward": self.total_reward,
                "efficiency": self.efficiency,
                "start_time": self.start_time,
                "uptime": time.time() - self.start_time,
                "history": list(self.metrics_history),
                "phase_configs": self.phase_configs,
                "phase_history": self.phase_history,
                "current_phase_metrics": self.current_phase_metrics,
                "channel_stats": dict(self.channel_stats),
                "vocab": [
                    {"id": v.token_id, "meaning": v.meaning, "category": v.category,
                     "freq": v.frequency, "phase": v.phase_discovered}
                    for v in self.vocab
                ],
                "last_eval": self.last_eval,
                "ep_rate": self._compute_rate(),
            }
    
    def _compute_rate(self) -> float:
        elapsed = time.time() - self.start_time
        return self.episode / elapsed if elapsed > 0 else 0.0
    
    def _push_event(self, event_type: str, data: dict) -> None:
        self._event_queue.append({
            "type": event_type,
            "data": data,
            "ts": time.time(),
        })
    
    def drain_events(self) -> list[dict]:
        """Pop all pending events (called by the server broadcast loop)."""
        with self._lock:
            events = list(self._event_queue)
            self._event_queue.clear()
            return events


# ────────────────────────────────────────────────────────────────
# FastAPI Application
# ────────────────────────────────────────────────────────────────

def create_app(bridge: TrainerBridge | None = None) -> FastAPI:
    """Create the FastAPI app with a TrainerBridge."""
    
    # ── Broadcast loop ─────────────────────────────────────────

    async def broadcast_loop():
        """Drain events from the bridge and push to all connected clients."""
        while True:
            events = bridge.drain_events()
            if events and app.state.ws_clients:
                dead = set()
                for ws in app.state.ws_clients:
                    for event in events:
                        try:
                            await ws.send_json(event)
                        except Exception:
                            dead.add(ws)
                            break
                app.state.ws_clients -= dead
            await asyncio.sleep(0.1)  # 10 Hz broadcast rate
    
    @asynccontextmanager
    async def lifespan(a):
        asyncio.create_task(broadcast_loop())
        logger.info("OGENTI Protocol Monitor server started")
        yield

    if bridge is None:
        bridge = TrainerBridge()
    
    app = FastAPI(
        title="OGENTI Protocol Monitor",
        version="0.1.0",
        docs_url="/api/docs",
        lifespan=lifespan,
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Store bridge on app state
    app.state.bridge = bridge
    app.state.ws_clients: set[WebSocket] = set()
    
    # ── WebSocket ──────────────────────────────────────────────
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        app.state.ws_clients.add(websocket)
        logger.info(f"WebSocket client connected. Total: {len(app.state.ws_clients)}")
        
        try:
            # Send full state snapshot on connect
            snapshot = bridge.snapshot()
            await websocket.send_json({"type": "state", "data": snapshot})
            
            # Keep alive + listen for commands
            while True:
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                    msg = json.loads(raw)
                    cmd = msg.get("cmd")
                    
                    if cmd == "pause":
                        bridge.pause()
                        await websocket.send_json({"type": "status", "data": {"status": bridge.status}})
                    elif cmd == "resume":
                        bridge.resume()
                        await websocket.send_json({"type": "status", "data": {"status": bridge.status}})
                    elif cmd == "ping":
                        await websocket.send_json({"type": "pong", "data": {"ts": time.time()}})
                    elif cmd == "snapshot":
                        snap = bridge.snapshot()
                        await websocket.send_json({"type": "state", "data": snap})
                    
                except asyncio.TimeoutError:
                    # Send heartbeat
                    try:
                        await websocket.send_json({
                            "type": "heartbeat",
                            "data": {
                                "episode": bridge.episode,
                                "status": bridge.status,
                                "ts": time.time(),
                            },
                        })
                    except Exception:
                        break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(f"WebSocket error: {e}")
        finally:
            app.state.ws_clients.discard(websocket)
            logger.info(f"WebSocket client disconnected. Total: {len(app.state.ws_clients)}")
    
    # ── REST API ───────────────────────────────────────────────
    
    @app.get("/api/status")
    async def api_status():
        return JSONResponse({
            "status": bridge.status,
            "episode": bridge.episode,
            "phase": bridge.phase,
            "phase_name": bridge.phase_name,
            "uptime": time.time() - bridge.start_time,
            "ep_rate": bridge._compute_rate(),
            "ws_clients": len(app.state.ws_clients),
        })
    
    @app.get("/api/metrics")
    async def api_metrics():
        return JSONResponse({
            "compression": bridge.compression,
            "fidelity": bridge.fidelity,
            "avg_tokens": bridge.avg_tokens,
            "budget": bridge.budget,
            "total_reward": bridge.total_reward,
            "history": list(bridge.metrics_history),
        })
    
    @app.get("/api/phases")
    async def api_phases():
        return JSONResponse({
            "current_phase": bridge.phase,
            "current_phase_name": bridge.phase_name,
            "configs": bridge.phase_configs,
            "history": bridge.phase_history,
            "current_metrics": bridge.current_phase_metrics,
        })
    
    @app.get("/api/channel")
    async def api_channel():
        return JSONResponse(bridge.channel_stats)
    
    @app.get("/api/vocab")
    async def api_vocab():
        return JSONResponse({
            "count": len(bridge.vocab),
            "tokens": [
                {"id": v.token_id, "meaning": v.meaning, "category": v.category,
                 "freq": v.frequency, "phase": v.phase_discovered}
                for v in bridge.vocab
            ],
        })
    
    @app.get("/api/snapshot")
    async def api_snapshot():
        return JSONResponse(bridge.snapshot())
    
    @app.post("/api/training/pause")
    async def api_pause():
        bridge.pause()
        return JSONResponse({"status": "paused"})
    
    @app.post("/api/training/resume")
    async def api_resume():
        bridge.resume()
        return JSONResponse({"status": "training"})
    
    # ── Static files (dashboard) ───────────────────────────────
    
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        @app.get("/")
        async def serve_index():
            return FileResponse(web_dir / "index.html")
        
        app.mount("/", StaticFiles(directory=str(web_dir)), name="static")
    
    return app


# ────────────────────────────────────────────────────────────────
# Server startup helpers
# ────────────────────────────────────────────────────────────────

def start_server(
    bridge: TrainerBridge | None = None,
    host: str = "0.0.0.0",
    port: int = 8000,
    log_level: str = "info",
) -> None:
    """Start the OGENTI monitoring server (blocking)."""
    import uvicorn
    
    app = create_app(bridge)
    uvicorn.run(app, host=host, port=port, log_level=log_level)


def start_server_background(
    bridge: TrainerBridge | None = None,
    host: str = "0.0.0.0",
    port: int = 8000,
) -> threading.Thread:
    """Start the server in a background thread (non-blocking)."""
    thread = threading.Thread(
        target=start_server,
        args=(bridge, host, port),
        daemon=True,
        name="ogenti-monitor",
    )
    thread.start()
    logger.info(f"Monitor server started at http://{host}:{port}")
    return thread


# ────────────────────────────────────────────────────────────────
# CLI entry point
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="OGENTI Protocol Monitor Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    parser.add_argument("--demo", action="store_true", help="Run with demo data generator")
    args = parser.parse_args()
    
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    
    bridge = TrainerBridge()
    
    if args.demo:
        # Start a background thread that feeds demo data into the bridge
        from ogenti_train._demo_feeder import start_demo_feeder
        start_demo_feeder(bridge)
    
    start_server(bridge, host=args.host, port=args.port, log_level=args.log_level)
