"""DB extension for the unified-ops view.

Adds three tables alongside the runs/steps/tool_calls schema in db.py:
  - jira_tickets        (received from webhooks, classified, linked to a job)
  - ops_events          (jenkins / spinnaker / github events on one timeline)
  - notification_rules  (which kinds of events fire browser notifications)

Reuses the same SQLite file (CARSON_DB env var) and the same write lock.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from .db import _connect, cursor, _row_to_dict, init_db as _init_runs


_OPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS jira_tickets (
    key            TEXT PRIMARY KEY,
    project        TEXT,
    summary        TEXT,
    description    TEXT,
    repo           TEXT,
    labels_json    TEXT,
    received_at    REAL NOT NULL,
    classified_at  REAL,
    track          TEXT,
    agent          TEXT,
    confidence     REAL,
    signals_json   TEXT,
    backend        TEXT,
    job_id         TEXT,
    raw_json       TEXT
);

CREATE TABLE IF NOT EXISTS ops_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    action        TEXT NOT NULL,
    target        TEXT,
    detail        TEXT,
    status        TEXT,
    team          TEXT,
    received_at   REAL NOT NULL,
    raw_json      TEXT
);

CREATE INDEX IF NOT EXISTS idx_jira_received ON jira_tickets(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_received  ON ops_events(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_source    ON ops_events(source, received_at DESC);

CREATE TABLE IF NOT EXISTS notification_rules (
    name        TEXT PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 1
);
"""

DEFAULT_RULES = [
    ("hitl_requested",     1),
    ("build_failed",       1),
    ("deploy_rolled_back", 1),
    ("pr_review_requested", 1),
    ("athena_stale_24h",   0),
    ("slo_burn_breach",    1),
    ("cost_budget_80",     0),
]


def init_ops_db() -> None:
    """Initialize runs schema + ops schema + default rules."""
    _init_runs()
    with cursor() as c:
        c.executescript(_OPS_SCHEMA)
        for name, enabled in DEFAULT_RULES:
            c.execute(
                "INSERT OR IGNORE INTO notification_rules (name, enabled) VALUES (?, ?)",
                (name, enabled),
            )


# ── Jira tickets ───────────────────────────────────────────────────────────


def upsert_ticket(ticket: dict[str, Any]) -> None:
    with cursor() as c:
        c.execute(
            """INSERT OR REPLACE INTO jira_tickets
               (key, project, summary, description, repo, labels_json,
                received_at, classified_at, track, agent, confidence,
                signals_json, backend, job_id, raw_json)
               VALUES (:key, :project, :summary, :description, :repo,
                       :labels_json, :received_at, :classified_at, :track,
                       :agent, :confidence, :signals_json, :backend, :job_id,
                       :raw_json)""",
            {
                "key": ticket["key"],
                "project": ticket.get("project"),
                "summary": ticket.get("summary"),
                "description": ticket.get("description"),
                "repo": ticket.get("repo"),
                "labels_json": json.dumps(ticket.get("labels", [])),
                "received_at": ticket.get("received_at", time.time()),
                "classified_at": ticket.get("classified_at"),
                "track": ticket.get("track"),
                "agent": ticket.get("agent"),
                "confidence": ticket.get("confidence"),
                "signals_json": json.dumps(ticket.get("signals", [])),
                "backend": ticket.get("backend"),
                "job_id": ticket.get("job_id"),
                "raw_json": json.dumps(ticket.get("raw") or {}),
            },
        )


def list_tickets(limit: int = 30, unrouted_only: bool = False) -> list[dict]:
    q = "SELECT * FROM jira_tickets"
    where = []
    if unrouted_only:
        where.append("track IS NULL")
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY received_at DESC LIMIT ?"
    with _connect() as c:
        rows = c.execute(q, (limit,)).fetchall()
    return [_unpack_ticket(r) for r in rows]


def _unpack_ticket(r: sqlite3.Row) -> dict:
    d = _row_to_dict(r)
    if d.get("labels_json"):
        try:
            d["labels"] = json.loads(d["labels_json"])
        except Exception:
            d["labels"] = []
    if d.get("signals_json"):
        try:
            d["signals"] = json.loads(d["signals_json"])
        except Exception:
            d["signals"] = []
    return d


# ── Ops events ─────────────────────────────────────────────────────────────


def insert_ops_event(ev: dict[str, Any]) -> int:
    with cursor() as c:
        cur = c.execute(
            """INSERT INTO ops_events
               (source, action, target, detail, status, team, received_at, raw_json)
               VALUES (:source, :action, :target, :detail, :status, :team,
                       :received_at, :raw_json)""",
            {
                "source": ev["source"],
                "action": ev["action"],
                "target": ev.get("target"),
                "detail": ev.get("detail"),
                "status": ev.get("status"),
                "team": ev.get("team"),
                "received_at": ev.get("received_at", time.time()),
                "raw_json": json.dumps(ev.get("raw") or {}),
            },
        )
        return cur.lastrowid


def list_ops_events(limit: int = 60, source: str | None = None,
                    team: str | None = None) -> list[dict]:
    q = "SELECT * FROM ops_events"
    where, args = [], []
    if source:
        where.append("source = ?"); args.append(source)
    if team:
        where.append("team = ?"); args.append(team)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY received_at DESC LIMIT ?"
    args.append(limit)
    with _connect() as c:
        rows = c.execute(q, args).fetchall()
    return [_row_to_dict(r) for r in rows]


# ── Notification rules ─────────────────────────────────────────────────────


def list_rules() -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT name, enabled FROM notification_rules ORDER BY name"
        ).fetchall()
    return [{"name": r["name"], "enabled": bool(r["enabled"])} for r in rows]


def set_rule(name: str, enabled: bool) -> None:
    with cursor() as c:
        c.execute(
            "INSERT INTO notification_rules (name, enabled) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET enabled = excluded.enabled",
            (name, 1 if enabled else 0),
        )


def is_rule_enabled(name: str) -> bool:
    with _connect() as c:
        row = c.execute(
            "SELECT enabled FROM notification_rules WHERE name = ?", (name,)
        ).fetchone()
    return bool(row and row["enabled"])
