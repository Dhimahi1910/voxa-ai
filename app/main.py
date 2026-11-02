from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.api import calls, customers, dashboard, jobs, webhooks
from app.container import build_services
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db import dispose_engine, init_engine
from app.scheduler import build_scheduler

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    sessions = init_engine(settings.database_url)
    app.state.services = sv = build_services(settings, sessions)
    log.info("starting", extra={"real_calls": settings.enable_real_calls, "email": settings.enable_email_sending,
                                "sheets_dry_run": settings.sheets_dry_run, "scheduler": settings.scheduler_enabled})
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = build_scheduler(sv)
        scheduler.start()  # pending tasks/calls are in the DB, so the first ticks recover anything left from a restart
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    await dispose_engine()


app = FastAPI(title="Voice Calling Agent", lifespan=lifespan)
app.include_router(calls.router)
app.include_router(customers.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(webhooks.router)


@app.get("/health")
async def health():
    s = get_settings()
    return {"status": "ok", "real_calls": s.enable_real_calls, "email_sending": s.enable_email_sending}


# Serve the built frontend (npm run build -> frontend/dist) from the same origin, after all API routes.
_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
