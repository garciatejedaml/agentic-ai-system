"""Autonomous jobs + Athena knowledge agents — DB schema + fixtures.

The dashboard's autonomous view shows two things side by side:

  1. autonomous_jobs   — coder/sdlc agents writing real code, phase by phase
  2. knowledge_agents  — Athena platform agents indexing/syncing knowledge

Tables live alongside the existing carson dashboard schema (ops_db.py),
sharing the same SQLite file (CARSON_DB env var).
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .db import _connect, cursor, _row_to_dict, init_db as _init_runs


PHASES = ["clone", "analyze", "generate", "test", "commit", "pr", "review", "build", "deploy"]

JOB_STATES = (
    "running",
    "awaiting_review",
    "awaiting_prod",
    "deploying",
    "held",
    "ok",
    "failed",
    "cancelled",
)

KNOWLEDGE_STATES = ("fresh", "syncing", "stale")


_AUTON_SCHEMA = """
CREATE TABLE IF NOT EXISTS autonomous_jobs (
    job_id          TEXT PRIMARY KEY,
    ticket_key      TEXT,
    summary         TEXT NOT NULL,
    branch          TEXT,
    user            TEXT,
    tags_json       TEXT,
    started_at      REAL NOT NULL,
    state           TEXT NOT NULL,
    state_label     TEXT,
    current_phase   TEXT,
    tokens          INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0,
    tests_passed    INTEGER DEFAULT 0,
    tests_total     INTEGER DEFAULT 0,
    files_modified  INTEGER DEFAULT 0,
    pr_number       TEXT,
    pr_status       TEXT
);

CREATE TABLE IF NOT EXISTS autonomous_phases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       TEXT NOT NULL REFERENCES autonomous_jobs(job_id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    phase        TEXT NOT NULL,
    status       TEXT NOT NULL,
    duration_s   REAL,
    started_at   REAL,
    ended_at     REAL,
    UNIQUE(job_id, seq)
);

CREATE TABLE IF NOT EXISTS knowledge_agents (
    name         TEXT PRIMARY KEY,
    chunks       INTEGER DEFAULT 0,
    chunks_total INTEGER,
    last_sync_at REAL,
    next_sync_at REAL,
    state        TEXT NOT NULL,
    detail       TEXT,
    sync_pct     INTEGER,
    sync_label   TEXT,
    activity_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_started ON autonomous_jobs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_phases_job   ON autonomous_phases(job_id, seq);
"""


def init_autonomous_db() -> None:
    _init_runs()
    with cursor() as c:
        c.executescript(_AUTON_SCHEMA)


# ── Jobs ────────────────────────────────────────────────────────────────


def upsert_job(job: dict[str, Any]) -> None:
    with cursor() as c:
        c.execute(
            """INSERT OR REPLACE INTO autonomous_jobs
               (job_id, ticket_key, summary, branch, user, tags_json,
                started_at, state, state_label, current_phase, tokens,
                cost_usd, tests_passed, tests_total, files_modified,
                pr_number, pr_status)
               VALUES (:job_id, :ticket_key, :summary, :branch, :user,
                       :tags_json, :started_at, :state, :state_label,
                       :current_phase, :tokens, :cost_usd, :tests_passed,
                       :tests_total, :files_modified, :pr_number, :pr_status)""",
            {
                "job_id": job["job_id"],
                "ticket_key": job.get("ticket_key"),
                "summary": job["summary"],
                "branch": job.get("branch"),
                "user": job.get("user"),
                "tags_json": json.dumps(job.get("tags", [])),
                "started_at": job.get("started_at", time.time()),
                "state": job["state"],
                "state_label": job.get("state_label"),
                "current_phase": job.get("current_phase"),
                "tokens": job.get("tokens", 0),
                "cost_usd": job.get("cost_usd", 0.0),
                "tests_passed": job.get("tests_passed", 0),
                "tests_total": job.get("tests_total", 0),
                "files_modified": job.get("files_modified", 0),
                "pr_number": job.get("pr_number"),
                "pr_status": job.get("pr_status"),
            },
        )


def upsert_phase(job_id: str, seq: int, phase: str, status: str,
                 duration_s: float | None = None,
                 started_at: float | None = None,
                 ended_at: float | None = None) -> None:
    with cursor() as c:
        c.execute(
            """INSERT INTO autonomous_phases
                 (job_id, seq, phase, status, duration_s, started_at, ended_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(job_id, seq) DO UPDATE SET
                 status = excluded.status,
                 duration_s = excluded.duration_s,
                 started_at = excluded.started_at,
                 ended_at = excluded.ended_at""",
            (job_id, seq, phase, status, duration_s, started_at, ended_at),
        )


def list_jobs(limit: int = 30) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM autonomous_jobs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        jobs = [_unpack_job(r) for r in rows]
        for j in jobs:
            phases = c.execute(
                "SELECT * FROM autonomous_phases WHERE job_id = ? ORDER BY seq",
                (j["job_id"],),
            ).fetchall()
            j["phases"] = [_row_to_dict(p) for p in phases]
    return jobs


def get_job(job_id: str) -> dict | None:
    with _connect() as c:
        row = c.execute(
            "SELECT * FROM autonomous_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not row:
            return None
        j = _unpack_job(row)
        phases = c.execute(
            "SELECT * FROM autonomous_phases WHERE job_id = ? ORDER BY seq",
            (job_id,),
        ).fetchall()
        j["phases"] = [_row_to_dict(p) for p in phases]
    return j


def update_job_state(job_id: str, state: str, state_label: str | None = None) -> None:
    with cursor() as c:
        c.execute(
            "UPDATE autonomous_jobs SET state = ?, state_label = COALESCE(?, state_label) "
            "WHERE job_id = ?",
            (state, state_label, job_id),
        )


def _unpack_job(r) -> dict:
    d = _row_to_dict(r)
    if d.get("tags_json"):
        try: d["tags"] = json.loads(d["tags_json"])
        except Exception: d["tags"] = []
    return d


# ── Knowledge agents ────────────────────────────────────────────────────


def upsert_knowledge_agent(agent: dict[str, Any]) -> None:
    with cursor() as c:
        c.execute(
            """INSERT OR REPLACE INTO knowledge_agents
               (name, chunks, chunks_total, last_sync_at, next_sync_at,
                state, detail, sync_pct, sync_label, activity_json)
               VALUES (:name, :chunks, :chunks_total, :last_sync_at,
                       :next_sync_at, :state, :detail, :sync_pct,
                       :sync_label, :activity_json)""",
            {
                "name": agent["name"],
                "chunks": agent.get("chunks", 0),
                "chunks_total": agent.get("chunks_total"),
                "last_sync_at": agent.get("last_sync_at"),
                "next_sync_at": agent.get("next_sync_at"),
                "state": agent.get("state", "fresh"),
                "detail": agent.get("detail"),
                "sync_pct": agent.get("sync_pct"),
                "sync_label": agent.get("sync_label"),
                "activity_json": json.dumps(agent.get("activity", [])),
            },
        )


def list_knowledge_agents() -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM knowledge_agents ORDER BY name"
        ).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        if d.get("activity_json"):
            try: d["activity"] = json.loads(d["activity_json"])
            except Exception: d["activity"] = []
        out.append(d)
    return out


# ── Fixture loader (used by simulator) ──────────────────────────────────


def seed_demo_state() -> None:
    """Populate autonomous_jobs / phases / knowledge_agents with the
    canonical mockup data — only if empty."""
    init_autonomous_db()
    with _connect() as c:
        existing = c.execute("SELECT COUNT(*) AS n FROM autonomous_jobs").fetchone()
        if existing and existing["n"]:
            return

    now = time.time()

    # ── Job 1 — running, phase 4 (test live)
    upsert_job({
        "job_id": "J-2418",
        "ticket_key": "CARSN-1289",
        "summary": "Add /metrics endpoint to svc-payments",
        "branch": "feat/carsn-1289-metrics-endpoint",
        "user": "martin@jpmc",
        "tags": ["coder", "athena"],
        "started_at": now - 4 * 60,
        "state": "running",
        "state_label": "running · phase 4 of 9",
        "current_phase": "test",
        "tokens": 12400,
        "cost_usd": 0.18,
        "tests_passed": 34,
        "tests_total": 47,
        "files_modified": 2,
    })
    _seed_phases("J-2418", [
        ("clone", "done", 180),
        ("analyze", "done", 42),
        ("generate", "done", 68),
        ("test", "live", None),
        ("commit", "pending", None),
        ("pr", "pending", None),
        ("review", "pending", None),
        ("build", "pending", None),
        ("deploy", "pending", None),
    ])

    # ── Job 2 — awaiting human review (HITL on phase 7)
    upsert_job({
        "job_id": "J-2417",
        "ticket_key": "CARSN-1287",
        "summary": "Refactor jira webhook handler · pull-out retry logic",
        "branch": "feat/carsn-1287-jira-webhook",
        "user": "alex@jpmc",
        "tags": ["coder"],
        "started_at": now - 28 * 60,
        "state": "awaiting_review",
        "state_label": "awaiting human review",
        "current_phase": "review",
        "tokens": 18700,
        "cost_usd": 0.24,
        "tests_passed": 89,
        "tests_total": 89,
        "files_modified": 5,
        "pr_number": "#4421",
        "pr_status": "open",
    })
    _seed_phases("J-2417", [
        ("clone", "done", 120),
        ("analyze", "done", 60),
        ("generate", "done", 134),
        ("test", "done", 110),
        ("commit", "done", 8),
        ("pr", "done", 22),
        ("review", "hitl", 23 * 60),
        ("build", "pending", None),
        ("deploy", "pending", None),
    ])

    # ── Job 3 — running phase 5 (commit live)
    upsert_job({
        "job_id": "J-2416",
        "ticket_key": "CARSN-1285",
        "summary": "Bump terraform module versions to v2.4 (vpc, iam-bound, ecs)",
        "branch": "feat/carsn-1285-tf-bump",
        "user": "sami@jpmc",
        "tags": ["coder", "terraform"],
        "started_at": now - 6 * 60,
        "state": "running",
        "state_label": "running · phase 5 of 9",
        "current_phase": "commit",
        "tokens": 9100,
        "cost_usd": 0.12,
        "tests_passed": 156,
        "tests_total": 156,
        "files_modified": 8,
    })
    _seed_phases("J-2416", [
        ("clone", "done", 110),
        ("analyze", "done", 38),
        ("generate", "done", 52),
        ("test", "done", 124),
        ("commit", "live", None),
        ("pr", "pending", None),
        ("review", "pending", None),
        ("build", "pending", None),
        ("deploy", "pending", None),
    ])

    # ── Job 4 — deploying to prod, awaiting prod approval
    upsert_job({
        "job_id": "J-2415",
        "ticket_key": "CARSN-1281",
        "summary": "Migrate Athena collection schema to v2 · add embedding model field",
        "branch": "feat/carsn-1281-athena-v2",
        "user": "martin@jpmc",
        "tags": ["coder", "athena"],
        "started_at": now - 47 * 60,
        "state": "awaiting_prod",
        "state_label": "deploying to prod · awaiting approval",
        "current_phase": "deploy",
        "tokens": 34200,
        "cost_usd": 0.51,
        "tests_passed": 312,
        "tests_total": 312,
        "files_modified": 14,
        "pr_number": "#4419",
        "pr_status": "merged",
    })
    _seed_phases("J-2415", [
        ("clone", "done", 120),
        ("analyze", "done", 60),
        ("generate", "done", 180),
        ("test", "done", 150),
        ("commit", "done", 12),
        ("pr", "done", 28),
        ("review", "done", 18 * 60),
        ("build", "done", 7 * 60),
        ("deploy", "hitl", 9 * 60),
    ])

    # ── Knowledge agents (Athena)
    KNOWLEDGE = [
        ("bob",     1024,  None, 12 * 60,  5 * 3600 + 48 * 60, "fresh",   "batch jobs domain", None, None,
         [3, 5, 4, 6, 7, 5, 8, 6]),
        ("hydra",   612,   None, 8 * 60,   5 * 3600 + 52 * 60, "fresh",   "arcDB / dbsync", None, None,
         [4, 5, 5, 4, 6, 5, 5, 4]),
        ("csb",     234,   890,  3 * 60,   None,                "syncing", "cdb / partition · started 1m 20s ago", 26, "26% done",
         [2, 3, 2, 4, 3, 5, 6, 7]),
        ("pixie",   89,    None, 60 * 60,  5 * 3600,            "fresh",   "graph / layer", None, None,
         [2, 2, 3, 2, 2, 3, 2, 2]),
        ("studio",  12,    None, 24 * 3600, 30 * 60,            "stale",   "warning · staging area", None, None,
         [1, 1, 2, 1, 1, 1, 0, 0]),
        ("sdlc",    178,   None, 4 * 3600, 2 * 3600,            "fresh",   "blessing / changeset", None, None,
         [3, 4, 3, 3, 4, 3, 4, 3]),
        ("aquiles", 45,    None, 30 * 60,  5 * 3600 + 30 * 60,  "fresh",   "ascode platform", None, None,
         [1, 2, 1, 2, 2, 1, 2, 2]),
    ]
    for name, chunks, total, last_off, next_off, state, detail, pct, label, act in KNOWLEDGE:
        upsert_knowledge_agent({
            "name": name,
            "chunks": chunks,
            "chunks_total": total,
            "last_sync_at": now - last_off if last_off is not None else None,
            "next_sync_at": now + next_off if next_off is not None else None,
            "state": state,
            "detail": detail,
            "sync_pct": pct,
            "sync_label": label,
            "activity": act,
        })


def _seed_phases(job_id: str, items: list[tuple]) -> None:
    for i, (phase, status, dur) in enumerate(items):
        upsert_phase(job_id, i, phase, status, duration_s=dur)
