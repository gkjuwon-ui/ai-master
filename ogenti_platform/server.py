"""O Series Platform — Main Server (Ogenti + Ovisen)"""
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import uvicorn

from .database import init_db, SessionLocal, TrainingJob, OVisenTrainingJob
from .auth import router as auth_router
from .billing import router as billing_router
from .api_keys import router as keys_router
from .training import router as training_router, _sync_job_from_runpod
from .adapter import router as adapter_router
from .ovisen_training import router as ovisen_training_router, _sync_ovisen_from_runpod
from .ovisen_adapter import router as ovisen_adapter_router
from .runpod_client import check_job_status
from .runpod_ovisen_client import check_ovisen_status

logger = logging.getLogger("oseries.server")

# ── App ──
app = FastAPI(
    title="O Series Platform",
    description="AI-to-AI Compression — OGENTI (Text Protocol) + OVISEN (Image Embeddings)",
    version="0.2.0",
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://oseries.io", "https://www.oseries.io", "http://localhost:3000", "http://localhost:8080"],
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
# OVISEN routes
app.include_router(ovisen_training_router)
app.include_router(ovisen_adapter_router)

# ── Static files ──
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/platform", StaticFiles(directory=str(STATIC_DIR), html=True), name="platform")

# ── Dashboard monitor (web/ folder) ──
WEB_DIR = Path(__file__).parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/monitor", StaticFiles(directory=str(WEB_DIR), html=True), name="monitor")


# ── Health ──
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "o-series-platform", "version": "0.2.0", "products": ["ogenti", "ovisen"]}


# ── Background RunPod Job Poller ──
async def _poll_runpod_jobs():
    """Background task: polls RunPod every 30s for active OGENTI + OVISEN jobs."""
    while True:
        await asyncio.sleep(30)
        try:
            db = SessionLocal()

            # Poll OGENTI jobs
            ogenti_jobs = (
                db.query(TrainingJob)
                .filter(TrainingJob.status.in_(["dispatched", "running"]))
                .filter(TrainingJob.runpod_request_id.isnot(None))
                .all()
            )
            for job in ogenti_jobs:
                try:
                    rp = check_job_status(job.runpod_request_id)
                    _sync_job_from_runpod(job, rp, db)
                except Exception as e:
                    logger.warning(f"Poller: failed to sync OGENTI job {job.id}: {e}")

            # Poll OVISEN jobs
            ovisen_jobs = (
                db.query(OVisenTrainingJob)
                .filter(OVisenTrainingJob.status.in_(["dispatched", "running"]))
                .filter(OVisenTrainingJob.runpod_request_id.isnot(None))
                .all()
            )
            for job in ovisen_jobs:
                try:
                    rp = check_ovisen_status(job.runpod_request_id)
                    _sync_ovisen_from_runpod(job, rp, db)
                except Exception as e:
                    logger.warning(f"Poller: failed to sync OVISEN job {job.id}: {e}")

            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Poller error: {e}")


# ── Init ──
@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(_poll_runpod_jobs())
    print("◆ O SERIES PLATFORM — ONLINE ◆")
    print("◆ Products: OGENTI (text) + OVISEN (image)")
    print("◆ RunPod job poller started (30s interval)")
    print("Dashboard: http://localhost:8080/platform/")


def main():
    from .config import HOST, PORT
    uvicorn.run("ogenti_platform.server:app", host=HOST, port=PORT, reload=True)
