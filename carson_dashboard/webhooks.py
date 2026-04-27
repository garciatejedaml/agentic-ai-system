"""Webhook receivers + classifier glue.

Each receiver:
  1. Persists the event (jira_tickets / ops_events).
  2. Publishes an SSE event on the bus so the dashboard updates live.
  3. Emits a `notify` event when an active rule matches — the browser
     turns these into Notification API calls.

The shapes are tolerant: receivers accept the raw provider payload (Jira
webhook, Jenkins notification plugin, Spinnaker echo, GitHub PR webhook)
and a simplified shape used by the simulator/tests. Anything we can't
parse defaults to a sensible label.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from . import ops_db
from .classifier import classify
from .stream import bus


# ── Jira ───────────────────────────────────────────────────────────────────


def receive_jira(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept a Jira webhook payload and route it to a Carson agent."""
    issue = payload.get("issue") or payload
    fields = issue.get("fields", {}) if isinstance(issue, dict) else {}
    key = issue.get("key") or payload.get("key") or _gen_key()

    summary = fields.get("summary") or payload.get("summary", "")
    description = fields.get("description") or payload.get("description", "")
    project_field = fields.get("project")
    project = (project_field or {}).get("key") if isinstance(project_field, dict) else payload.get("project")
    labels = fields.get("labels") or payload.get("labels") or []
    repo = payload.get("repo")

    received_at = time.time()
    bus.publish({
        "type": "jira.received",
        "key": key,
        "summary": summary,
        "project": project,
    })

    cls = classify({
        "summary": summary,
        "description": description,
        "project": project,
        "labels": labels,
        "repo": repo,
    })
    classified_at = time.time()
    job_id = "J-" + uuid.uuid4().hex[:6].upper()

    ticket = {
        "key": key,
        "project": project,
        "summary": summary,
        "description": description,
        "repo": repo,
        "labels": labels,
        "received_at": received_at,
        "classified_at": classified_at,
        "track": cls.track,
        "agent": cls.agent,
        "confidence": cls.confidence,
        "signals": cls.signals,
        "backend": cls.backend,
        "job_id": job_id,
        "raw": payload,
    }
    ops_db.upsert_ticket(ticket)

    bus.publish({
        "type": "jira.routed",
        "key": key,
        "track": cls.track,
        "agent": cls.agent,
        "confidence": cls.confidence,
        "signals": cls.signals,
        "job_id": job_id,
        "summary": summary,
        "backend": cls.backend,
    })

    return {
        "key": key, "job_id": job_id, "track": cls.track, "agent": cls.agent,
        "confidence": cls.confidence, "signals": cls.signals, "backend": cls.backend,
    }


# ── Jenkins ────────────────────────────────────────────────────────────────


def receive_jenkins(payload: dict[str, Any]) -> dict[str, Any]:
    """Jenkins notification plugin payload (or simplified shape)."""
    name = payload.get("name") or payload.get("job") or "?"
    build = payload.get("build") if isinstance(payload.get("build"), dict) else {}
    number = build.get("number") or payload.get("number")
    phase = (build.get("phase") or payload.get("phase") or "completed").lower()
    result = (build.get("status") or payload.get("result") or "success").lower()
    team = payload.get("team")

    if phase in ("started", "queued"):
        action, status = "build_started", "run"
    elif result in ("success", "ok"):
        action, status = "build_ok", "ok"
    else:
        action, status = "build_fail", "fail"

    detail = f"{name} · #{number}" if number else name
    return _record_ops("jenkins", action, name, detail, status, team, payload)


# ── Spinnaker ──────────────────────────────────────────────────────────────


def receive_spinnaker(payload: dict[str, Any]) -> dict[str, Any]:
    """Spinnaker echo / pipeline notification payload."""
    pipeline = payload.get("application") or payload.get("pipeline") or "?"
    env = payload.get("environment") or "—"
    status_in = (payload.get("status") or payload.get("eventType") or "").lower()
    team = payload.get("team")

    if "rollback" in status_in or "rolled" in status_in:
        action, status = "rolled_back", "fail"
    elif "succeed" in status_in or "complete" in status_in:
        action, status = "deploy_ok", "ok"
    elif "fail" in status_in:
        action, status = "deploy_fail", "fail"
    else:
        action, status = "deploy_started", "run"

    detail = f"{pipeline} · {env}"
    return _record_ops("spinnaker", action, pipeline, detail, status, team, payload)


# ── GitHub / Bitbucket PRs ─────────────────────────────────────────────────


def receive_github(payload: dict[str, Any]) -> dict[str, Any]:
    """GitHub PR webhook payload."""
    pr = payload.get("pull_request") or {}
    repo = (payload.get("repository") or {}).get("name") or pr.get("repo") or "?"
    number = pr.get("number") or payload.get("number")
    action_in = (payload.get("action") or "opened").lower()
    team = payload.get("team")
    sender = payload.get("sender") or {}
    actor = sender.get("login") or pr.get("user")

    if action_in == "opened":
        action, status = "pr_opened", "run"
    elif action_in == "review_requested":
        action, status = "review_requested", "run"
    elif action_in == "closed" and pr.get("merged"):
        action, status = "pr_merged", "merged"
    elif action_in == "closed":
        action, status = "pr_closed", "fail"
    else:
        action, status = f"pr_{action_in}", "ok"

    detail_parts = [f"PR #{number}"] if number else []
    detail_parts.append(repo)
    if actor:
        detail_parts.append(actor)
    detail = " · ".join(detail_parts)
    return _record_ops("github", action, repo, detail, status, team, payload)


# ── HITL ───────────────────────────────────────────────────────────────────


def request_hitl(job_id: str, summary: str) -> None:
    """Carson agents call this when they need a human approval."""
    bus.publish({"type": "hitl.requested", "job_id": job_id, "summary": summary})
    if ops_db.is_rule_enabled("hitl_requested"):
        bus.publish({
            "type": "notify",
            "rule": "hitl_requested",
            "title": "HITL approval needed",
            "body": f"{job_id} · {summary}",
            "tag": f"carson-hitl-{job_id}",
        })


# ── Internal ───────────────────────────────────────────────────────────────


def _record_ops(source: str, action: str, target: str, detail: str,
                status: str, team: str | None, raw: dict) -> dict:
    ev = {
        "source": source,
        "action": action,
        "target": target,
        "detail": detail,
        "status": status,
        "team": team,
        "received_at": time.time(),
        "raw": raw,
    }
    ev_id = ops_db.insert_ops_event(ev)
    bus.publish({"type": "ops.event", "id": ev_id, **ev})

    # Notification rules → notify events
    rule_map = {
        "build_fail":   ("build_failed", "Build failed"),
        "rolled_back":  ("deploy_rolled_back", "Deploy rolled back"),
        "review_requested": ("pr_review_requested", "PR review requested"),
    }
    if action in rule_map:
        rule_name, title = rule_map[action]
        if ops_db.is_rule_enabled(rule_name):
            bus.publish({
                "type": "notify",
                "rule": rule_name,
                "title": title,
                "body": detail,
                "tag": f"carson-{rule_name}-{ev_id}",
            })

    return {"id": ev_id, **ev}


def _gen_key() -> str:
    return "CRED-" + uuid.uuid4().hex[:4].upper()
