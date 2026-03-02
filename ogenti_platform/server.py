"""Ogenti Platform — Main Server"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import uvicorn

from .database import init_db
from .auth import router as auth_router
from .billing import router as billing_router
from .api_keys import router as keys_router
from .training import router as training_router
from .adapter import router as adapter_router

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


# ── Init ──
@app.on_event("startup")
async def startup():
    init_db()
    print("◆ OGENTI PLATFORM — ONLINE ◆")
    print("Dashboard: http://localhost:8080/platform/")


def main():
    from .config import HOST, PORT
    uvicorn.run("ogenti_platform.server:app", host=HOST, port=PORT, reload=True)
