"""
server.py — PHIREN Training Monitor Server

FastAPI + WebSocket server for real-time training observation.
Follows ogenti_train.server pattern (TrainerBridge + REST/WS).

Endpoints:
  WS  /ws              — live event stream
  GET /api/status       — current training status
  GET /api/metrics      — recent metrics
  GET /api/phases       — curriculum phases
  GET /api/channel      — verification channel stats
  GET /api/snapshot     — full state snapshot
  POST /api/pause       — pause training
  POST /api/resume      — resume training
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import threading
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Trainer Bridge
# ─────────────────────────────────────────────────────────────────

class PhirenTrainerBridge:
    """
    Thread-safe bridge between the trainer and the monitor server.

    The trainer pushes events; the server reads and broadcasts.
    """

    def __init__(self, max_events: int = 5000):
        self._lock = threading.Lock()
        self._events: deque = deque(maxlen=max_events)

        # State
        self.status = "idle"  # idle | training | paused | complete
        self.current_episode = 0
        self.total_episodes = 0
        self.current_phase = 0
        self.phase_name = ""
        self.best_factuality = 0.0

        # Recent metrics
        self._metrics: deque = deque(maxlen=1000)

        # Pause/resume
        self._paused = threading.Event()
        self._paused.set()  # not paused initially

    def on_episode(
        self,
        episode: int,
        reward: float,
        metrics: Optional[dict] = None,
    ) -> None:
        """Called by trainer after each episode."""
        with self._lock:
            self.current_episode = episode
            self.status = "training"

            event = {
                "type": "episode",
                "episode": episode,
                "reward": round(reward, 4),
                "timestamp": time.time(),
            }
            if metrics:
                event["metrics"] = {
                    k: round(v, 4) if isinstance(v, float) else v
                    for k, v in metrics.items()
                }
                self._metrics.append(event["metrics"])

            self._events.append(event)

    def on_phase_change(
        self,
        old_phase: int,
        new_phase: int,
    ) -> None:
        """Called by trainer on phase transition."""
        with self._lock:
            self.current_phase = new_phase
            event = {
                "type": "phase_change",
                "old_phase": old_phase,
                "new_phase": new_phase,
                "timestamp": time.time(),
            }
            self._events.append(event)

    def on_eval(self, metrics: dict) -> None:
        """Called by trainer on evaluation."""
        with self._lock:
            event = {
                "type": "eval",
                "metrics": metrics,
                "timestamp": time.time(),
            }
            self._events.append(event)

    def on_training_end(self, results: dict) -> None:
        """Called when training completes."""
        with self._lock:
            self.status = "complete"
            event = {
                "type": "training_end",
                "results": results,
                "timestamp": time.time(),
            }
            self._events.append(event)

    def get_events(self, since_idx: int = 0) -> list[dict]:
        """Get events since a given index."""
        with self._lock:
            events = list(self._events)
            return events[since_idx:]

    def snapshot(self) -> dict:
        """Full state snapshot for late joiners."""
        with self._lock:
            return {
                "status": self.status,
                "current_episode": self.current_episode,
                "total_episodes": self.total_episodes,
                "current_phase": self.current_phase,
                "phase_name": self.phase_name,
                "best_factuality": self.best_factuality,
                "num_events": len(self._events),
                "recent_metrics": list(self._metrics)[-10:],
            }

    def pause(self) -> None:
        self._paused.clear()
        with self._lock:
            self.status = "paused"

    def resume(self) -> None:
        self._paused.set()
        with self._lock:
            self.status = "training"

    def wait_if_paused(self) -> None:
        """Called by trainer to block if paused."""
        self._paused.wait()


# ─────────────────────────────────────────────────────────────────
#  FastAPI Application
# ─────────────────────────────────────────────────────────────────

def create_app(bridge: PhirenTrainerBridge):
    """Create FastAPI app with WebSocket + REST endpoints."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError("pip install fastapi uvicorn")

    app = FastAPI(title="PHIREN Training Monitor", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # WebSocket connections
    connected_clients: list[WebSocket] = []

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        connected_clients.append(websocket)
        logger.info(f"Monitor client connected ({len(connected_clients)} total)")

        # Send initial snapshot
        try:
            await websocket.send_json({
                "type": "snapshot",
                "data": bridge.snapshot(),
            })

            event_idx = len(bridge._events)

            while True:
                await asyncio.sleep(0.1)  # 10Hz polling

                new_events = bridge.get_events(event_idx)
                if new_events:
                    for event in new_events:
                        try:
                            await websocket.send_json(event)
                        except Exception:
                            break
                    event_idx += len(new_events)

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug(f"WebSocket error: {e}")
        finally:
            if websocket in connected_clients:
                connected_clients.remove(websocket)
            logger.info(f"Monitor client disconnected ({len(connected_clients)} total)")

    @app.get("/api/status")
    async def get_status():
        return bridge.snapshot()

    @app.get("/api/metrics")
    async def get_metrics():
        return {"metrics": list(bridge._metrics)[-100:]}

    @app.get("/api/phases")
    async def get_phases():
        return {
            "current_phase": bridge.current_phase,
            "phase_name": bridge.phase_name,
        }

    @app.get("/api/snapshot")
    async def get_snapshot():
        return bridge.snapshot()

    @app.post("/api/pause")
    async def pause_training():
        bridge.pause()
        return {"status": "paused"}

    @app.post("/api/resume")
    async def resume_training():
        bridge.resume()
        return {"status": "resumed"}

    return app


# ─────────────────────────────────────────────────────────────────
#  Server Startup
# ─────────────────────────────────────────────────────────────────

def start_server(
    bridge: PhirenTrainerBridge,
    host: str = "0.0.0.0",
    port: int = 8765,
) -> None:
    """Start the monitor server (blocking)."""
    import uvicorn

    app = create_app(bridge)
    logger.info(f"Starting PHIREN monitor server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def start_server_background(
    bridge: PhirenTrainerBridge,
    host: str = "0.0.0.0",
    port: int = 8765,
) -> threading.Thread:
    """Start the monitor server in a background thread."""
    thread = threading.Thread(
        target=start_server,
        args=(bridge, host, port),
        daemon=True,
        name="phiren-monitor",
    )
    thread.start()
    logger.info(f"PHIREN monitor server started in background on {host}:{port}")
    return thread
