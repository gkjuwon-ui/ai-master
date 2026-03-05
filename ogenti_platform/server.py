"""Series Platform — Main Server (O-Series: Ogenti/Ovisen, P-Series: Phiren/Parhen, M-Series: Murhen)"""
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import uvicorn

from .database import init_db, SessionLocal, TrainingJob, OVisenTrainingJob, PhirenTrainingJob
from .auth import router as auth_router
from .billing import router as billing_router
from .api_keys import router as keys_router
from .training import router as training_router, _sync_job_from_runpod
from .adapter import router as adapter_router
from .ovisen_training import router as ovisen_training_router, _sync_ovisen_from_runpod
from .ovisen_adapter import router as ovisen_adapter_router
from .phiren_training import router as phiren_training_router, _sync_phiren_from_runpod
from .phiren_adapter import router as phiren_adapter_router
from .runpod_client import check_job_status
from .runpod_ovisen_client import check_ovisen_status
from .runpod_phiren_client import check_phiren_status

logger = logging.getLogger("series.server")

# ── App ──
app = FastAPI(
    title="Series Platform",
    description="AI Adapter Studio — O-Series (OGENTI Text + OVISEN Image) · P-Series (PHIREN Hallucination Guard + PARHEN Anti-Sycophancy) · M-Series (MURHEN Position-Agnostic Recall)",
    version="0.4.0",
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://series.so", "https://www.series.so", "https://oseries.io", "https://www.oseries.io", "http://localhost:3000", "http://localhost:8080"],
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
# PHIREN routes
app.include_router(phiren_training_router)
app.include_router(phiren_adapter_router)

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
    return {"status": "ok", "service": "series-platform", "version": "0.4.0", "products": {"o-series": ["ogenti", "ovisen"], "p-series": ["phiren", "parhen"], "m-series": ["murhen"]}}


# ── Root redirect ──
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(
        '<html><head><meta http-equiv="refresh" content="0;url=/platform/login.html"></head></html>',
        status_code=302,
        headers={"Location": "/platform/login.html"},
    )


# ── Background RunPod Job Poller ──
async def _poll_runpod_jobs():
    """Background task: polls RunPod every 30s for active OGENTI + OVISEN + PHIREN jobs."""
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

            # Poll PHIREN jobs
            phiren_jobs = (
                db.query(PhirenTrainingJob)
                .filter(PhirenTrainingJob.status.in_(["dispatched", "running"]))
                .filter(PhirenTrainingJob.runpod_request_id.isnot(None))
                .all()
            )
            for job in phiren_jobs:
                try:
                    rp = check_phiren_status(job.runpod_request_id)
                    _sync_phiren_from_runpod(job, rp, db)
                except Exception as e:
                    logger.warning(f"Poller: failed to sync PHIREN job {job.id}: {e}")

            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Poller error: {e}")


# ── Init ──
@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(_poll_runpod_jobs())
    print("◆ SERIES PLATFORM — ONLINE ◆")
    print("◆ O-Series: OGENTI (text) + OVISEN (image)")
    print("◆ P-Series: PHIREN (hallucination guard)")
    print("◆ RunPod job poller started (30s interval)")
    print("Dashboard: http://localhost:8080/platform/")


def main():
    from .config import HOST, PORT
    uvicorn.run("ogenti_platform.server:app", host=HOST, port=PORT, reload=True)
