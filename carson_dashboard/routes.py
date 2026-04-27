"""FastAPI routes for the Carson dashboard."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import db
from .stream import bus, serialize

router = APIRouter()

STATIC_DIR = Path(__file__).parent / "static"


@router.get("/dashboard", include_in_schema=False)
async def dashboard_home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/api/health")
async def health() -> dict:
    return {"ok": True, "listeners": bus.listener_count}


@router.get("/api/runs")
async def api_runs(limit: int = 50, since_hours: float | None = None) -> JSONResponse:
    since = (time.time() - since_hours * 3600) if since_hours else None
    return JSONResponse(db.list_runs(limit=limit, since=since))


@router.get("/api/runs/{run_id}")
async def api_run_detail(run_id: str) -> JSONResponse:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, f"run {run_id} not found")
    return JSONResponse(run)


@router.get("/api/stats")
async def api_stats(window_hours: float = 168.0) -> JSONResponse:
    seconds = window_hours * 3600
    return JSONResponse({
        "window_hours": window_hours,
        "aggregate": db.aggregate_window(seconds),
        "by_agent": db.agent_stats(seconds),
    })


@router.get("/sse")
async def sse_stream() -> EventSourceResponse:
    async def gen():
        async for event in bus.subscribe():
            yield {"event": event.get("type", "message"), "data": serialize(event)}
    return EventSourceResponse(gen())


def mount_static(app) -> None:
    """Call once after include_router to serve the static folder."""
    app.mount(
        "/dashboard/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="dashboard_static",
    )
