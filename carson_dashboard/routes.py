"""FastAPI routes for the Carson dashboard."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import autonomous, db, ops_db, webhooks
from .stream import bus, serialize

router = APIRouter()

STATIC_DIR = Path(__file__).parent / "static"


# ── Pages ──────────────────────────────────────────────────────────────────


@router.get("/dashboard", include_in_schema=False)
async def dashboard_home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# ── Health / runs / stats ──────────────────────────────────────────────────


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


# ── Jira intake / classification ───────────────────────────────────────────


@router.get("/api/jira/tickets")
async def api_list_tickets(limit: int = 30) -> JSONResponse:
    return JSONResponse(ops_db.list_tickets(limit=limit))


@router.post("/api/jira/webhook")
async def api_jira_webhook(payload: dict = Body(...)) -> JSONResponse:
    """Real Jira webhook target. Configure in Jira Admin → System →
    WebHooks. URL: https://<carson-host>/api/jira/webhook"""
    result = webhooks.receive_jira(payload)
    return JSONResponse(result)


@router.post("/api/jira/classify")
async def api_jira_classify(payload: dict = Body(...)) -> JSONResponse:
    """Classify-only endpoint (no persistence) for previews/tests."""
    from .classifier import classify
    cls = classify(payload)
    return JSONResponse(cls.to_dict())


# ── Ops feed (Jenkins / Spinnaker / GitHub) ────────────────────────────────


@router.get("/api/ops/events")
async def api_ops_events(
    limit: int = 60,
    source: str | None = None,
    team: str | None = None,
) -> JSONResponse:
    return JSONResponse(ops_db.list_ops_events(limit=limit, source=source, team=team))


@router.post("/api/ops/jenkins/webhook")
async def api_jenkins_webhook(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(webhooks.receive_jenkins(payload))


@router.post("/api/ops/spinnaker/webhook")
async def api_spinnaker_webhook(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(webhooks.receive_spinnaker(payload))


@router.post("/api/ops/github/webhook")
async def api_github_webhook(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(webhooks.receive_github(payload))


# ── Notification rules ─────────────────────────────────────────────────────


@router.get("/api/notifications/rules")
async def api_list_rules() -> JSONResponse:
    return JSONResponse(ops_db.list_rules())


@router.post("/api/notifications/rules/{name}")
async def api_set_rule(name: str, payload: dict = Body(...)) -> JSONResponse:
    enabled = bool(payload.get("enabled", True))
    ops_db.set_rule(name, enabled)
    bus.publish({"type": "rule.changed", "name": name, "enabled": enabled})
    return JSONResponse({"name": name, "enabled": enabled})


# ── HITL ───────────────────────────────────────────────────────────────────


@router.post("/api/hitl/request")
async def api_hitl_request(payload: dict = Body(...)) -> JSONResponse:
    """Carson agents call this when they need a human approval."""
    job_id = payload.get("job_id") or "J-?"
    summary = payload.get("summary") or "approval needed"
    webhooks.request_hitl(job_id, summary)
    return JSONResponse({"ok": True, "job_id": job_id})


# ── Autonomous jobs + Athena knowledge agents ──────────────────────────────


@router.get("/api/autonomous/jobs")
async def api_autonomous_jobs(limit: int = 30) -> JSONResponse:
    return JSONResponse(autonomous.list_jobs(limit=limit))


@router.get("/api/autonomous/jobs/{job_id}")
async def api_autonomous_job_detail(job_id: str) -> JSONResponse:
    job = autonomous.get_job(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    return JSONResponse(job)


@router.post("/api/autonomous/jobs/{job_id}/{action}")
async def api_autonomous_job_action(job_id: str, action: str,
                                    payload: dict = Body(default={})) -> JSONResponse:
    """approve | reject | cancel | hold | resume → state transition + SSE"""
    valid = {"approve", "reject", "cancel", "hold", "resume", "approve_prod"}
    if action not in valid:
        raise HTTPException(400, f"unknown action {action}")
    job = autonomous.get_job(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    state_map = {
        "approve":      ("running", "approved · resuming"),
        "approve_prod": ("deploying", "approved · deploying to prod"),
        "reject":       ("failed", "rejected by reviewer"),
        "cancel":       ("cancelled", "cancelled"),
        "hold":         ("held", "held by operator"),
        "resume":       ("running", "resumed"),
    }
    new_state, label = state_map[action]
    autonomous.update_job_state(job_id, new_state, label)
    bus.publish({"type": "autonomous.state",
                 "job_id": job_id, "state": new_state, "label": label,
                 "actor": payload.get("actor")})
    return JSONResponse({"job_id": job_id, "state": new_state, "label": label})


@router.get("/api/autonomous/agents")
async def api_knowledge_agents() -> JSONResponse:
    return JSONResponse(autonomous.list_knowledge_agents())


# ── SSE ────────────────────────────────────────────────────────────────────


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
