"""FastAPI routes for the Carson dashboard."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import audit, autonomous, chats, db, metrics, ops_db, pm, replay, webhooks
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


# ── Cost / impact ──────────────────────────────────────────────────────────


@router.get("/api/cost/summary")
async def api_cost_summary(window_days: float = 90.0) -> JSONResponse:
    return JSONResponse(metrics.cost_summary(window_days=window_days))


@router.get("/api/cost/comparison")
async def api_cost_comparison() -> JSONResponse:
    return JSONResponse(metrics.comparison())


@router.get("/api/cost/autonomy-trend")
async def api_autonomy_trend(weeks: int = 12) -> JSONResponse:
    return JSONResponse(metrics.autonomy_trend(weeks=weeks))


@router.get("/api/cost/leaderboard")
async def api_leaderboard(limit: int = 10) -> JSONResponse:
    return JSONResponse(metrics.leaderboard(limit=limit))


# ── Autonomy view ──────────────────────────────────────────────────────────


@router.get("/api/autonomy/summary")
async def api_autonomy_summary() -> JSONResponse:
    return JSONResponse(metrics.autonomy_summary())


@router.get("/api/autonomy/skills")
async def api_skills() -> JSONResponse:
    return JSONResponse(metrics.skills())


# ── Replay / time-travel ───────────────────────────────────────────────────


@router.get("/api/replay/recent")
async def api_replay_recent(limit: int = 20) -> JSONResponse:
    return JSONResponse(replay.list_recent_runs(limit=limit))


@router.get("/api/replay/{run_id}/timeline")
async def api_replay_timeline(run_id: str) -> JSONResponse:
    tl = replay.get_timeline(run_id)
    if not tl:
        raise HTTPException(404, f"run {run_id} not found")
    return JSONResponse(tl)


# ── Audit / compliance ─────────────────────────────────────────────────────


@router.get("/api/audit/log")
async def api_audit_log(
    limit: int = 100,
    since_hours: float | None = None,
    types: str | None = None,
    actor: str | None = None,
) -> JSONResponse:
    since = (time.time() - since_hours * 3600) if since_hours else None
    type_list = types.split(",") if types else None
    return JSONResponse(audit.list_audit(
        limit=limit, since=since, event_types=type_list, actor=actor
    ))


@router.get("/api/audit/stats")
async def api_audit_stats(window_days: float = 7.0) -> JSONResponse:
    return JSONResponse(audit.audit_stats(window_days=window_days))


@router.post("/api/audit/export")
async def api_audit_export(payload: dict = Body(default={})) -> JSONResponse:
    since_hours = payload.get("since_hours", 30 * 24)
    since = time.time() - since_hours * 3600
    return JSONResponse(audit.export_summary(since=since))


# ── Multi-session chat ─────────────────────────────────────────────────────


@router.get("/api/chats")
async def api_chats_list() -> JSONResponse:
    return JSONResponse(chats.list_sessions())


@router.post("/api/chats")
async def api_chats_create(payload: dict = Body(...)) -> JSONResponse:
    title = payload.get("title") or "untitled"
    focus = payload.get("agent_focus", "general")
    owner = payload.get("owner")
    s = chats.create_session(title, agent_focus=focus, owner=owner)
    bus.publish({"type": "chat.session_created", "session_id": s["id"]})
    return JSONResponse(s)


@router.get("/api/chats/{session_id}")
async def api_chats_session(session_id: str) -> JSONResponse:
    s = chats.get_session(session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return JSONResponse(s)


@router.get("/api/chats/{session_id}/messages")
async def api_chats_messages(session_id: str, limit: int = 200) -> JSONResponse:
    chats.mark_read(session_id)
    return JSONResponse(chats.list_messages(session_id, limit=limit))


@router.post("/api/chats/{session_id}/messages")
async def api_chats_send(session_id: str, payload: dict = Body(...)) -> JSONResponse:
    """Append a user message; mock router classifies + replies.
    Real Carson replaces the body with a langgraph dispatch."""
    text = payload.get("text", "")
    name = payload.get("name", "you")
    msg_id = chats.append_message(session_id, {
        "type": "user", "name": name, "text": text,
    })
    bus.publish({"type": "chat.user_message", "session_id": session_id,
                 "id": msg_id, "name": name, "text": text})
    return JSONResponse({"ok": True, "id": msg_id})


@router.post("/api/chats/{session_id}/pin")
async def api_chats_pin(session_id: str, payload: dict = Body(default={})) -> JSONResponse:
    chats.pin_session(session_id, bool(payload.get("pinned", True)))
    return JSONResponse({"ok": True})


@router.delete("/api/chats/{session_id}")
async def api_chats_archive(session_id: str) -> JSONResponse:
    chats.archive_session(session_id)
    return JSONResponse({"ok": True})


# ── Project Manager ────────────────────────────────────────────────────────


@router.get("/api/pm/projects")
async def api_pm_projects() -> JSONResponse:
    return JSONResponse(pm.list_projects())


@router.post("/api/pm/projects")
async def api_pm_create_project(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(pm.create_project(
        name=payload["name"],
        code=payload.get("code"),
        quarter=payload.get("quarter"),
    ))


@router.get("/api/pm/epics")
async def api_pm_epics(project_id: str | None = None,
                       state: str | None = None) -> JSONResponse:
    return JSONResponse(pm.list_epics(project_id=project_id, state=state))


@router.post("/api/pm/epics")
async def api_pm_create_epic(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(pm.create_epic(
        project_id=payload["project_id"],
        title=payload["title"],
        summary=payload.get("summary"),
        owner=payload.get("owner"),
        target_date=payload.get("target_date"),
        jira_key=payload.get("jira_key"),
    ))


@router.get("/api/pm/deliverables")
async def api_pm_deliverables(epic_id: str | None = None) -> JSONResponse:
    return JSONResponse(pm.list_deliverables(epic_id=epic_id))


@router.post("/api/pm/deliverables")
async def api_pm_create_deliverable(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(pm.create_deliverable(
        epic_id=payload["epic_id"],
        title=payload["title"],
        owner=payload.get("owner"),
        points=payload.get("points"),
        jira_key=payload.get("jira_key"),
    ))


@router.get("/api/pm/confluence")
async def api_pm_confluence(space: str | None = None,
                             project_id: str | None = None) -> JSONResponse:
    return JSONResponse(pm.list_confluence(space=space, project_id=project_id))


@router.post("/api/pm/draft/epic")
async def api_pm_draft_epic(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(pm.draft_epic(
        description=payload["description"],
        project_id=payload.get("project_id"),
    ))


@router.post("/api/pm/draft/jira")
async def api_pm_draft_jira(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(pm.draft_jira(
        description=payload["description"],
        parent_epic=payload.get("parent_epic"),
    ))


@router.post("/api/pm/draft/confluence")
async def api_pm_draft_confluence(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(pm.draft_confluence(
        description=payload["description"],
        space=payload.get("space", "GENERAL"),
    ))


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
