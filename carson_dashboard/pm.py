"""Project Manager view backend.

Three tables:
  pm_projects     — top-level container (e.g. CREDITTECH-2026-Q4)
  pm_epics        — multi-ticket initiatives belonging to a project
  pm_deliverables — concrete child items of an epic, mapped to Jira

Plus confluence_pages: discovered/synced docs, lightly indexed for the
PM view's left rail.

The "draft" endpoints (draft_epic, draft_jira, draft_confluence) accept
natural language and return a structured proposal that the user can
review and accept. In the dashboard wireup, accepting commits the
real Jira/Confluence record via the existing ops webhooks.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .db import _connect, cursor, _row_to_dict


_PM_SCHEMA = """
CREATE TABLE IF NOT EXISTS pm_projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    code          TEXT,
    quarter       TEXT,
    state         TEXT NOT NULL DEFAULT 'active',
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pm_epics (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES pm_projects(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    summary       TEXT,
    state         TEXT NOT NULL DEFAULT 'backlog',
    owner         TEXT,
    jira_key      TEXT,
    target_date   TEXT,
    progress_pct  REAL DEFAULT 0,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pm_deliverables (
    id            TEXT PRIMARY KEY,
    epic_id       TEXT NOT NULL REFERENCES pm_epics(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    state         TEXT NOT NULL DEFAULT 'backlog',
    owner         TEXT,
    jira_key      TEXT,
    points        INTEGER,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS confluence_pages (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    space         TEXT NOT NULL,
    url           TEXT,
    last_edited_at REAL,
    last_editor   TEXT,
    summary       TEXT,
    project_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_pm_epics_project ON pm_epics(project_id, state);
CREATE INDEX IF NOT EXISTS idx_pm_deliv_epic   ON pm_deliverables(epic_id, state);
CREATE INDEX IF NOT EXISTS idx_conf_space      ON confluence_pages(space, last_edited_at DESC);
"""

EPIC_STATES = ("backlog", "planning", "in_progress", "review", "done", "cancelled")
DELIVERABLE_STATES = ("backlog", "in_progress", "review", "blocked", "done")


def init_pm_db() -> None:
    with cursor() as c:
        c.executescript(_PM_SCHEMA)


# ── Projects ────────────────────────────────────────────────────────────


def list_projects() -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM pm_projects ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_project(name: str, code: str | None = None, quarter: str | None = None) -> dict:
    pid = "prj-" + uuid.uuid4().hex[:6]
    with cursor() as c:
        c.execute(
            "INSERT INTO pm_projects (id, name, code, quarter, state, created_at) "
            "VALUES (?, ?, ?, ?, 'active', ?)",
            (pid, name, code, quarter, time.time()),
        )
    return {"id": pid, "name": name, "code": code, "quarter": quarter, "state": "active"}


# ── Epics ───────────────────────────────────────────────────────────────


def list_epics(project_id: str | None = None, state: str | None = None) -> list[dict]:
    q = "SELECT * FROM pm_epics"
    where, args = [], []
    if project_id:
        where.append("project_id = ?"); args.append(project_id)
    if state:
        where.append("state = ?"); args.append(state)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY created_at DESC"
    with _connect() as c:
        rows = c.execute(q, args).fetchall()
    epics = [_row_to_dict(r) for r in rows]
    # attach deliverable counts
    with _connect() as c:
        for e in epics:
            counts = c.execute(
                """SELECT state, COUNT(*) AS n FROM pm_deliverables
                   WHERE epic_id = ? GROUP BY state""",
                (e["id"],),
            ).fetchall()
            e["deliverable_counts"] = {r["state"]: r["n"] for r in counts}
    return epics


def create_epic(project_id: str, title: str, summary: str | None = None,
                owner: str | None = None, target_date: str | None = None,
                jira_key: str | None = None) -> dict:
    eid = "epic-" + uuid.uuid4().hex[:6]
    with cursor() as c:
        c.execute(
            """INSERT INTO pm_epics
               (id, project_id, title, summary, owner, target_date, jira_key,
                state, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'planning', ?)""",
            (eid, project_id, title, summary, owner, target_date, jira_key, time.time()),
        )
    return {"id": eid, "title": title, "summary": summary, "state": "planning"}


# ── Deliverables ────────────────────────────────────────────────────────


def list_deliverables(epic_id: str | None = None) -> list[dict]:
    q = "SELECT * FROM pm_deliverables"
    args = []
    if epic_id:
        q += " WHERE epic_id = ?"; args.append(epic_id)
    q += " ORDER BY created_at DESC"
    with _connect() as c:
        rows = c.execute(q, args).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_deliverable(epic_id: str, title: str, owner: str | None = None,
                       points: int | None = None,
                       jira_key: str | None = None) -> dict:
    did = "del-" + uuid.uuid4().hex[:6]
    with cursor() as c:
        c.execute(
            """INSERT INTO pm_deliverables
               (id, epic_id, title, owner, points, jira_key, state, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'backlog', ?)""",
            (did, epic_id, title, owner, points, jira_key, time.time()),
        )
    return {"id": did, "title": title, "state": "backlog"}


# ── Confluence pages ────────────────────────────────────────────────────


def list_confluence(space: str | None = None,
                    project_id: str | None = None) -> list[dict]:
    q = "SELECT * FROM confluence_pages"
    where, args = [], []
    if space:
        where.append("space = ?"); args.append(space)
    if project_id:
        where.append("project_id = ?"); args.append(project_id)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY last_edited_at DESC"
    with _connect() as c:
        rows = c.execute(q, args).fetchall()
    return [_row_to_dict(r) for r in rows]


def upsert_confluence(page: dict[str, Any]) -> None:
    pid = page.get("id") or "conf-" + uuid.uuid4().hex[:6]
    with cursor() as c:
        c.execute(
            """INSERT OR REPLACE INTO confluence_pages
               (id, title, space, url, last_edited_at, last_editor, summary, project_id)
               VALUES (:id, :title, :space, :url, :last_edited_at, :last_editor, :summary, :project_id)""",
            {
                "id": pid,
                "title": page["title"],
                "space": page.get("space", "GENERAL"),
                "url": page.get("url"),
                "last_edited_at": page.get("last_edited_at", time.time()),
                "last_editor": page.get("last_editor"),
                "summary": page.get("summary"),
                "project_id": page.get("project_id"),
            },
        )


# ── AI drafts (used by PM chat / quick replies) ─────────────────────────


def draft_epic(description: str, project_id: str | None = None) -> dict:
    """Mock 'AI drafted this epic' — when wired, an LLM generates the
    structured proposal from the natural-language description."""
    title = description.strip().rstrip(".").capitalize()
    if len(title) > 80:
        title = title[:77] + "..."
    return {
        "title": title,
        "summary": f"Proposed epic generated from: \"{description[:120]}\"",
        "owner": "tbd",
        "target_date": _quarter_end(),
        "child_deliverables": [
            {"title": "Discovery + scoping",          "points": 3},
            {"title": "Architecture decision record", "points": 2},
            {"title": "Implementation",                "points": 8},
            {"title": "Migration plan",                "points": 3},
            {"title": "Validation + post-mortem",      "points": 2},
        ],
        "estimated_jira_key": "CARSN-" + str(_next_carsn()),
        "confluence_pages_to_create": [
            {"title": title + " · ADR", "space": "ARCH"},
            {"title": title + " · runbook", "space": "RUN"},
        ],
    }


def draft_jira(description: str, parent_epic: str | None = None) -> dict:
    title = description.strip().rstrip(".").capitalize()
    if len(title) > 80:
        title = title[:77] + "..."
    return {
        "title": title,
        "type": "Story",
        "priority": "Medium",
        "estimated_points": 3,
        "labels": ["backend"],
        "parent_epic": parent_epic,
        "estimated_key": "CARSN-" + str(_next_carsn()),
    }


def draft_confluence(description: str, space: str = "GENERAL") -> dict:
    title = description.strip().rstrip(".").capitalize()
    return {
        "title": title,
        "space": space,
        "outline": [
            {"heading": "Context", "level": 2},
            {"heading": "Decision", "level": 2},
            {"heading": "Consequences", "level": 2},
            {"heading": "Open questions", "level": 2},
        ],
        "estimated_url": "/wiki/spaces/" + space + "/pages/" + uuid.uuid4().hex[:6],
    }


def _quarter_end() -> str:
    import datetime as dt
    today = dt.date.today()
    q = (today.month - 1) // 3 + 1
    end_month = q * 3
    return f"{today.year}-{end_month:02d}-30"


def _next_carsn() -> int:
    return int(time.time()) % 10_000


# ── Fixtures ────────────────────────────────────────────────────────────


def seed_demo() -> None:
    init_pm_db()
    with _connect() as c:
        if c.execute("SELECT COUNT(*) AS n FROM pm_projects").fetchone()["n"]:
            return
    p = create_project("CREDITTECH-2026-Q4", code="CT26Q4", quarter="2026-Q4")
    pid = p["id"]
    epics_data = [
        ("Migrate Athena collection schema to v2", "Adds embedding model field, updates 7 athena agents.", "martin@jpmc", 0.78, "in_progress", "CARSN-1281"),
        ("Retire legacy infra modules", "Sunset 4 unused terraform modules + their pipelines.", "sami@jpmc", 0.42, "in_progress", "CARSN-1300"),
        ("HNSW index upgrade across athena", "Move all athena agents from flat to HNSW for 5x recall.", "alex@jpmc", 0.91, "review", "CARSN-1295"),
        ("CARSN webhook handler refactor", "Pull retry logic into RetryConfig — applies to 12 endpoints.", "alex@jpmc", 1.0, "done", "CARSN-1287"),
        ("Q1 2027 planning", "Carve up Q1 deliverables across teams.", "tbd", 0.10, "planning", None),
    ]
    epic_ids = []
    for title, summary, owner, prog, state, jk in epics_data:
        eid = "epic-" + uuid.uuid4().hex[:6]
        with cursor() as c:
            c.execute(
                """INSERT INTO pm_epics
                   (id, project_id, title, summary, owner, jira_key,
                    state, progress_pct, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, pid, title, summary, owner, jk, state, prog, time.time()),
            )
        epic_ids.append(eid)
    # deliverables for first epic
    deliverables_data = [
        (epic_ids[0], "Add embedding_model field", "aquiles", 3, "done", "CARSN-1289"),
        (epic_ids[0], "Migrate Athena Bob index",  "bob",     5, "in_progress", "CARSN-1290"),
        (epic_ids[0], "Migrate Athena Hydra",      "hydra",   3, "in_progress", "CARSN-1291"),
        (epic_ids[0], "Validation + cutover",      "martin@jpmc", 2, "backlog", None),
        (epic_ids[1], "Drop tf-aws-vpc-legacy",   "sami@jpmc",   2, "in_progress", "CARSN-1301"),
        (epic_ids[1], "Drop tf-aws-iam-shim",     "sami@jpmc",   2, "review", "CARSN-1302"),
        (epic_ids[1], "Drop tf-aws-eks-old",      "sdlc",        3, "backlog", "CARSN-1303"),
        (epic_ids[1], "Cleanup pipelines",         "sdlc",        2, "backlog", None),
        (epic_ids[2], "Migrate athena-bob to HNSW", "bob",       5, "done", "CARSN-1296"),
        (epic_ids[2], "Migrate athena-hydra",      "hydra",      3, "done", "CARSN-1297"),
        (epic_ids[2], "Migrate athena-csb",        "csb",        3, "review", "CARSN-1298"),
        (epic_ids[2], "Migrate athena-pixie",      "pixie",      3, "review", "CARSN-1299"),
    ]
    for epic_id, title, owner, points, state, jk in deliverables_data:
        with cursor() as c:
            c.execute(
                """INSERT INTO pm_deliverables
                   (id, epic_id, title, owner, points, jira_key, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("del-" + uuid.uuid4().hex[:6], epic_id, title, owner, points, jk, state, time.time()),
            )
    # confluence pages
    conf_data = [
        ("Athena schema v2 — ADR",      "ARCH", "alex@jpmc", -3 * 86400, "Decision record for the v2 schema migration"),
        ("Athena schema v2 — runbook",  "RUN",  "alex@jpmc", -2 * 86400, "Migration runbook step-by-step"),
        ("Carson autonomous agents — overview", "ARCH", "martin@jpmc", -7 * 86400, "How Carson agents work end-to-end"),
        ("Q4 retro 2026", "POSTMORTEM", "martin@jpmc", -1 * 86400, "What worked, what didn't"),
        ("HNSW migration plan", "ARCH", "alex@jpmc", -10 * 86400, "Plan + risks"),
        ("Webhook retry policy", "ARCH", "aquiles", -5 * 86400, "RetryConfig design + edge cases"),
    ]
    now = time.time()
    for title, space, editor, off, summary in conf_data:
        upsert_confluence({
            "title": title,
            "space": space,
            "last_editor": editor,
            "last_edited_at": now + off,
            "summary": summary,
            "project_id": pid,
            "url": "/wiki/spaces/" + space + "/pages/" + uuid.uuid4().hex[:6],
        })
