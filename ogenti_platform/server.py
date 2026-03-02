"""Ogenti Platform — Main Server"""
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import uvicorn

from .database import init_db, SessionLocal, TrainingJob
from .auth import router as auth_router
from .billing import router as billing_router
from .api_keys import router as keys_router
from .training import router as training_router, _sync_job_from_runpod
from .adapter import router as adapter_router
from .runpod_client import check_job_status

logger = logging.getLogger("ogenti.server")

# ── App ──
app = FastAPI(
    title="Ogenti Platform",
    description="AI-to-AI Communication Protocol — Training Platform",
    version="0.1.0",
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ogenti.com", "http://localhost:3000", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ──
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(keys_router)
app.include_router(training_router)
app.include_router(adapter_router)

# ── Static files ──
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/platform", StaticFiles(directory=str(STATIC_DIR), html=True), name="platform")


# ── Health ──
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ogenti-platform", "version": "0.1.0"}


# ── Background RunPod Job Poller ──
async def _poll_runpod_jobs():
    """Background task: polls RunPod every 30s for active training jobs."""
    while True:
        await asyncio.sleep(30)
        try:
            db = SessionLocal()
            active_jobs = (
                db.query(TrainingJob)
                .filter(TrainingJob.status.in_(["dispatched", "running"]))
                .filter(TrainingJob.runpod_request_id.isnot(None))
                .all()
            )
            for job in active_jobs:
                try:
                    rp = check_job_status(job.runpod_request_id)
                    _sync_job_from_runpod(job, rp, db)
                except Exception as e:
                    logger.warning(f"Poller: failed to sync job {job.id}: {e}")
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Poller error: {e}")


# ── Init ──
@app.on_event("startup")
async def startup():
    init_db()
    # Start background poller for RunPod jobs
    asyncio.create_task(_poll_runpod_jobs())
    print("◆ OGENTI PLATFORM — ONLINE ◆")
    print("◆ RunPod job poller started (30s interval)")
    print("Dashboard: http://localhost:8080/platform/")


def main():
    from .config import HOST, PORT
    uvicorn.run("ogenti_platform.server:app", host=HOST, port=PORT, reload=True)
