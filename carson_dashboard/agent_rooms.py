"""Agent rooms + Strands intermediate trace.

Each Carson agent gets its own "room" (WhatsApp-style group) and its
recent activity is rendered as a chat thread of strands events:

    system | user_message | routing | thinking | tool_call |
    tool_result | delegation | hitl_request | agent_message

The schema is two tables on the existing SQLite file:
  - agent_rooms      — one row per agent (name, role, color, presence,
                       pinned, last_msg, current_job, unread)
  - strands_events   — append-only event log per room/job; the room's
                       current trace is the latest events for the
                       active job_id

Designed for direct read by the dashboard (`/api/agent-rooms`) and
for live updates via SSE (`agent_room.event` event type).
"""
from __future__ import annotations

import json
import time
from typing import Any

from .db import _connect, cursor, _row_to_dict


PRESENCE = ("on", "idle", "hitl", "stale")
EVENT_TYPES = (
    "system",
    "user_message",
    "routing",
    "thinking",
    "tool_call",
    "tool_result",
    "delegation",
    "hitl_request",
    "agent_message",
)


_ROOMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_rooms (
    name              TEXT PRIMARY KEY,
    title             TEXT,
    agent             TEXT,
    role              TEXT,
    color             TEXT,
    track             TEXT,
    presence          TEXT NOT NULL DEFAULT 'idle',
    pinned            INTEGER DEFAULT 0,
    job_id            TEXT,
    last_msg_at       REAL,
    last_msg_preview  TEXT,
    last_msg_kind     TEXT,
    unread_count      INTEGER DEFAULT 0,
    state_label       TEXT,
    created_at        REAL,
    archived          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS strands_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    room          TEXT NOT NULL REFERENCES agent_rooms(name) ON DELETE CASCADE,
    job_id        TEXT,
    seq           INTEGER NOT NULL,
    event_type    TEXT NOT NULL,
    actor         TEXT,
    payload_json  TEXT,
    duration_ms   INTEGER,
    tokens        INTEGER,
    ts            REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rooms_pinned ON agent_rooms(pinned DESC, last_msg_at DESC);
CREATE INDEX IF NOT EXISTS idx_strands_room ON strands_events(room, ts);
CREATE INDEX IF NOT EXISTS idx_strands_job  ON strands_events(job_id, seq);
"""


def init_rooms_db() -> None:
    with cursor() as c:
        c.executescript(_ROOMS_SCHEMA)


# ── Rooms ───────────────────────────────────────────────────────────────


def upsert_room(room: dict[str, Any]) -> None:
    with cursor() as c:
        c.execute(
            """INSERT OR REPLACE INTO agent_rooms
               (name, title, agent, role, color, track, presence, pinned,
                job_id, last_msg_at, last_msg_preview, last_msg_kind,
                unread_count, state_label, created_at, archived)
               VALUES (:name, :title, :agent, :role, :color, :track,
                       :presence, :pinned, :job_id, :last_msg_at,
                       :last_msg_preview, :last_msg_kind, :unread_count,
                       :state_label, :created_at, :archived)""",
            {
                "name": room["name"],
                "title": room.get("title") or room["name"],
                "agent": room.get("agent") or room["name"],
                "role": room.get("role"),
                "color": room.get("color"),
                "track": room.get("track"),
                "presence": room.get("presence", "idle"),
                "pinned": 1 if room.get("pinned") else 0,
                "job_id": room.get("job_id"),
                "last_msg_at": room.get("last_msg_at", time.time()),
                "last_msg_preview": room.get("last_msg_preview"),
                "last_msg_kind": room.get("last_msg_kind"),
                "unread_count": room.get("unread_count", 0),
                "state_label": room.get("state_label"),
                "created_at": room.get("created_at", time.time()),
                "archived": 1 if room.get("archived") else 0,
            },
        )


# ── Agent registry (for "+ new room" UI) ────────────────────────────────


AGENT_REGISTRY = [
    {"agent": "aquiles",    "role": "coder · code agent",   "track": "coder",  "color": "#7c9cff"},
    {"agent": "sdlc",       "role": "coder · ci/release",   "track": "coder",  "color": "#c69bff"},
    {"agent": "brandson",   "role": "git agent",            "track": "git",    "color": "#a78bfa"},
    {"agent": "jenkins",    "role": "build agent",          "track": "build",  "color": "#5cd0c4"},
    {"agent": "spinnaker",  "role": "deploy agent",         "track": "deploy", "color": "#74d9a2"},
    {"agent": "inspector",  "role": "terraform agent",      "track": "infra",  "color": "#ffb059"},
    {"agent": "confluence", "role": "docs agent",           "track": "docs",   "color": "#c69bff"},
    {"agent": "jira",       "role": "tickets agent",        "track": "jira",   "color": "#ff8fb3"},
    {"agent": "bob",        "role": "athena · borrowing",   "track": "athena", "color": "#74d9a2"},
    {"agent": "hydra",      "role": "athena · decision",    "track": "athena", "color": "#5cd0c4"},
    {"agent": "csb",        "role": "athena · syndicate",   "track": "athena", "color": "#9aa0b3"},
    {"agent": "pixie",      "role": "athena · pricing",     "track": "athena", "color": "#ff8fb3"},
    {"agent": "studio",     "role": "athena · ml store",    "track": "athena", "color": "#ffb059"},
    {"agent": "router",     "role": "let the router decide", "track": "router", "color": "#7c9cff"},
]


def list_agent_registry() -> list[dict]:
    return list(AGENT_REGISTRY)


def find_agent(agent_name: str) -> dict | None:
    for a in AGENT_REGISTRY:
        if a["agent"] == agent_name:
            return a
    return None


def create_room(title: str, agent: str | None = None) -> dict:
    """Spin up a new dynamic room. Returns the created room dict.

    If agent is None or 'router', the room defers to the router which
    picks the actual agent on the first user message.
    """
    import uuid
    room_id = "ar-" + uuid.uuid4().hex[:8]
    info = find_agent(agent) if agent else None
    if not info:
        info = find_agent("router") or AGENT_REGISTRY[0]
    upsert_room({
        "name": room_id,
        "title": title or (info["agent"] + " · new conversation"),
        "agent": info["agent"],
        "role": info["role"],
        "color": info["color"],
        "track": info["track"],
        "presence": "idle",
        "state_label": "ready · waiting on first message",
    })
    append_event({
        "room": room_id,
        "event_type": "system",
        "payload": {"text": "room created · agent " + info["agent"]},
    })
    return get_room(room_id)


def list_rooms(include_archived: bool = False) -> list[dict]:
    q = "SELECT * FROM agent_rooms"
    if not include_archived:
        q += " WHERE archived = 0"
    q += " ORDER BY pinned DESC, last_msg_at DESC NULLS LAST"
    with _connect() as c:
        rows = c.execute(q).fetchall()
    return [_row_to_dict(r) for r in rows]


def archive_room(name: str) -> None:
    update_room(name, archived=1)


def get_room(name: str) -> dict | None:
    with _connect() as c:
        row = c.execute("SELECT * FROM agent_rooms WHERE name = ?", (name,)).fetchone()
    return _row_to_dict(row) if row else None


def update_room(name: str, **fields) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k} = :{k}" for k in fields)
    with cursor() as c:
        c.execute(
            f"UPDATE agent_rooms SET {keys} WHERE name = :n",
            {**fields, "n": name},
        )


def mark_read(name: str) -> None:
    update_room(name, unread_count=0)


def pin_room(name: str, pinned: bool) -> None:
    update_room(name, pinned=1 if pinned else 0)


# ── Strands events ──────────────────────────────────────────────────────


def append_event(ev: dict[str, Any]) -> int:
    """Append one event to a room's trace. Auto-seq.
    Updates the room's last_msg_* + unread_count."""
    room = ev["room"]
    with cursor() as c:
        seq_row = c.execute(
            "SELECT COALESCE(MAX(seq), 0) AS s FROM strands_events WHERE room = ?",
            (room,),
        ).fetchone()
        next_seq = (seq_row["s"] or 0) + 1
        ts = ev.get("ts", time.time())
        cur = c.execute(
            """INSERT INTO strands_events
               (room, job_id, seq, event_type, actor, payload_json,
                duration_ms, tokens, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                room,
                ev.get("job_id"),
                next_seq,
                ev["event_type"],
                ev.get("actor"),
                json.dumps(ev.get("payload", {})),
                ev.get("duration_ms"),
                ev.get("tokens"),
                ts,
            ),
        )
        # update room metadata
        preview = _preview_for(ev)
        c.execute(
            """UPDATE agent_rooms SET
                  last_msg_at = ?, last_msg_preview = ?, last_msg_kind = ?,
                  unread_count = unread_count + ?
               WHERE name = ?""",
            (ts, preview, ev["event_type"],
             1 if ev["event_type"] == "hitl_request" else 0, room),
        )
        return cur.lastrowid


def list_events(room: str, job_id: str | None = None,
                limit: int = 200) -> list[dict]:
    q = "SELECT * FROM strands_events WHERE room = ?"
    args = [room]
    if job_id:
        q += " AND job_id = ?"
        args.append(job_id)
    q += " ORDER BY ts ASC, seq ASC LIMIT ?"
    args.append(limit)
    with _connect() as c:
        rows = c.execute(q, args).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        if d.get("payload_json"):
            try:
                d["payload"] = json.loads(d["payload_json"])
            except Exception:
                d["payload"] = {}
        out.append(d)
    return out


def _preview_for(ev: dict) -> str:
    et = ev["event_type"]
    p = ev.get("payload", {})
    if et == "user_message":
        return (p.get("text") or "")[:120]
    if et == "agent_message":
        return (p.get("text") or "")[:120]
    if et == "thinking":
        return "thinking · " + (p.get("kind") or "step")
    if et == "tool_call":
        target = p.get("tool", "")
        return f"tool · {target}"
    if et == "tool_result":
        return f"result · {p.get('tool', '')} · {p.get('summary', '')[:60]}"
    if et == "delegation":
        return f"delegate → {p.get('to', '')}"
    if et == "hitl_request":
        return "awaiting human · " + (p.get("text") or "")[:80]
    if et == "routing":
        return f"router → {p.get('agent', '')}"
    return et


# ── Demo seed ───────────────────────────────────────────────────────────


_AQUILES_TRACE = [
    {"event_type": "system",
     "payload": {"text": "room opened · run J-2417 · CARSN-1287"},
     "offset": 0},
    {"event_type": "user_message",
     "actor": "martin",
     "payload": {"text": "Refactor the jira webhook handler · pull the retry logic into its own module."},
     "offset": 5},
    {"event_type": "routing",
     "payload": {"track": "coder", "agent": "aquiles", "confidence": 0.94,
                 "mode": "non_deterministic"},
     "offset": 7},
    {"event_type": "thinking",
     "actor": "aquiles",
     "payload": {"kind": "plan",
                 "text": "I need to find the existing retry logic first. The webhook handler probably calls _dispatch with a manual retry loop. I'll pull it out into a RetryConfig with explicit backoff, then wire the handler to use the new module."},
     "duration_ms": 1200, "tokens": 412,
     "offset": 12},
    {"event_type": "tool_call",
     "actor": "aquiles",
     "payload": {"tool": "github.read_file", "step": "1/8",
                 "args": {"repo": "jpmc/credit-tech",
                          "path": "payments/webhook_handler.py",
                          "ref": "main"}},
     "duration_ms": 400,
     "offset": 14},
    {"event_type": "tool_result",
     "actor": "aquiles",
     "payload": {"tool": "github.read_file", "status": "ok",
                 "summary": "3 retry sites identified at lines 14-20, 87-93, 154-160",
                 "size_kb": 7.4, "lines": 213},
     "offset": 15},
    {"event_type": "delegation",
     "actor": "aquiles",
     "payload": {"to": "brandson",
                 "text": "create branch feat/carsn-1287-jira-webhook from main@a4f12b"},
     "offset": 18},
    {"event_type": "thinking",
     "actor": "aquiles",
     "payload": {"kind": "synthesis",
                 "text": "Now I'll write the RetryConfig dataclass with maxRetries, backoff, retriable exceptions, and a retry_with_policy helper. Then refactor handle_webhook to call retry_with_policy(lambda: _dispatch(payload), cfg=RetryConfig.default(), retriable=(RetriableError, TimeoutError))."},
     "duration_ms": 2800, "tokens": 1047,
     "offset": 25},
    {"event_type": "tool_call",
     "actor": "aquiles",
     "payload": {"tool": "github.write_file", "step": "4/8",
                 "args": {"path": "payments/retry_config.py",
                          "content": "@dataclass\nclass RetryConfig: ...",
                          "branch": "feat/carsn-1287-jira-webhook",
                          "commit_msg": "Extract retry logic into RetryConfig"}},
     "duration_ms": 600,
     "offset": 28},
    {"event_type": "tool_result",
     "actor": "aquiles",
     "payload": {"tool": "github.write_file", "status": "ok",
                 "summary": "created retry_config.py · committed to feat/carsn-1287-jira-webhook",
                 "commit": "fb190a", "lines": 47},
     "offset": 29},
    {"event_type": "tool_call",
     "actor": "aquiles",
     "payload": {"tool": "github.run_tests", "step": "6/8",
                 "args": {"suite": "test_webhook",
                          "branch": "feat/carsn-1287-jira-webhook",
                          "timeout_s": 300}},
     "duration_ms": 110_000,
     "offset": 60},
    {"event_type": "tool_result",
     "actor": "aquiles",
     "payload": {"tool": "github.run_tests", "status": "ok",
                 "summary": "89 / 89 tests pass · 0 lint · 0 breaking changes · 5 files modified"},
     "offset": 170},
    {"event_type": "tool_call",
     "actor": "aquiles",
     "payload": {"tool": "github.create_pr", "step": "8/8",
                 "args": {"title": "Refactor: pull retry logic into RetryConfig",
                          "body": "Auto-generated. Closes CARSN-1287.",
                          "branch": "feat/carsn-1287-jira-webhook",
                          "reviewers": ["m.koch"]}},
     "duration_ms": 700,
     "offset": 175},
    {"event_type": "tool_result",
     "actor": "aquiles",
     "payload": {"tool": "github.create_pr", "status": "ok",
                 "summary": "opened PR #4421 · auto-review green · awaiting human",
                 "pr_number": "#4421"},
     "offset": 176},
    {"event_type": "hitl_request",
     "actor": "aquiles",
     "payload": {"job_id": "J-2417",
                 "text": "PR #4421 is ready for human review. 89/89 tests pass, no lint, no breaking changes, 5 files modified. Want me to merge or hold for your review?",
                 "actions": [
                     {"label": "merge now", "kind": "primary", "action": "approve"},
                     {"label": "I'll review first", "kind": "ghost", "action": "hold"},
                     {"label": "view PR ↗", "kind": "ghost", "action": "view"},
                 ]},
     "offset": 180},
]


_SDLC_TRACE = [
    {"event_type": "system",
     "payload": {"text": "room opened · run J-2416 · CARSN-1285"},
     "offset": 0},
    {"event_type": "user_message", "actor": "sami",
     "payload": {"text": "Bump terraform module versions to v2.4 (vpc, iam-bound, ecs)"},
     "offset": 4},
    {"event_type": "routing",
     "payload": {"track": "coder", "agent": "sdlc", "confidence": 0.91,
                 "mode": "deterministic"},
     "offset": 5},
    {"event_type": "thinking", "actor": "sdlc",
     "payload": {"kind": "plan",
                 "text": "Reading the existing module versions from the lockfile. Bumping to v2.4 and running terraform plan before opening the PR."},
     "duration_ms": 900, "tokens": 320,
     "offset": 10},
    {"event_type": "tool_call", "actor": "sdlc",
     "payload": {"tool": "terraform.read_lockfile", "step": "1/9",
                 "args": {"path": ".terraform.lock.hcl"}},
     "duration_ms": 300, "offset": 11},
    {"event_type": "tool_result", "actor": "sdlc",
     "payload": {"tool": "terraform.read_lockfile", "status": "ok",
                 "summary": "found 12 providers, 3 affected by v2.4 bump"},
     "offset": 12},
    {"event_type": "tool_call", "actor": "sdlc",
     "payload": {"tool": "terraform.plan", "step": "5/9",
                 "args": {"vars": {"env": "staging"}}},
     "duration_ms": 45_000, "offset": 35},
    {"event_type": "agent_message", "actor": "sdlc",
     "payload": {"text": "currently running plan · expect ~1m"},
     "offset": 36},
]

_BOB_TRACE = [
    {"event_type": "system",
     "payload": {"text": "room opened · scheduled sync after schema change"},
     "offset": 0},
    {"event_type": "agent_message", "actor": "bob",
     "payload": {"text": "Heads up — BOB hasn't refreshed since 12m ago. The schema bump on credit-decision may have stale embeddings. Sync now? ~5 min.",
                 "actions": [
                     {"label": "refresh now", "kind": "primary", "action": "refresh"},
                     {"label": "wait until prod hours", "kind": "ghost", "action": "dismiss"},
                 ]},
     "offset": 60},
    {"event_type": "user_message", "actor": "martin",
     "payload": {"text": "refresh now"},
     "offset": 90},
    {"event_type": "tool_call", "actor": "bob",
     "payload": {"tool": "athena.reindex",
                 "args": {"collection": "bob.borrowing", "scope": "credit-decision"}},
     "duration_ms": 300_000, "offset": 95},
    {"event_type": "agent_message", "actor": "bob",
     "payload": {"text": "starting sync now · expected 5 min · I'll let you know when fresh."},
     "offset": 96},
]

_HYDRA_TRACE = [
    {"event_type": "agent_message", "actor": "hydra",
     "payload": {"text": "FYI for whoever is reviewing the webhook PR — the new RetryConfig shape lands in the same module my decision agent reads. I'll need to re-sync after the merge. Want me to schedule it?",
                 "actions": [
                     {"label": "schedule for after merge", "kind": "primary", "action": "schedule"},
                     {"label": "sync now anyway", "kind": "ghost", "action": "sync"},
                 ]},
     "offset": 0},
]

_BRANDSON_TRACE = [
    {"event_type": "system",
     "payload": {"text": "delegated from aquiles · J-2417"},
     "offset": 0},
    {"event_type": "tool_call", "actor": "brandson",
     "payload": {"tool": "git.create_branch",
                 "args": {"name": "feat/carsn-1287-jira-webhook", "from": "main@a4f12b"}},
     "duration_ms": 200, "offset": 1},
    {"event_type": "tool_result", "actor": "brandson",
     "payload": {"tool": "git.create_branch", "status": "ok",
                 "summary": "branch created · resolved 4b4966b on origin/main · safe"},
     "offset": 1},
]

_STUDIO_TRACE = [
    {"event_type": "system",
     "payload": {"text": "stale · last sync 24h ago"},
     "offset": 0},
    {"event_type": "agent_message", "actor": "studio",
     "payload": {"text": "I'm stale. The Q2 catalog update arrived 24h ago and my embeddings haven't been refreshed. 12 chunks total, all from before the catalog drift."},
     "offset": 5},
]


def seed_demo_rooms() -> None:
    init_rooms_db()
    with _connect() as c:
        if c.execute("SELECT COUNT(*) AS n FROM agent_rooms").fetchone()["n"]:
            return

    now = time.time()

    # Aquiles · primary, pinned, with rich trace + HITL
    upsert_room({
        "name": "aquiles", "role": "coder · code agent",
        "color": "#7c9cff", "track": "coder",
        "presence": "hitl", "pinned": True, "job_id": "J-2417",
        "state_label": "awaiting human review",
    })
    _ingest_trace("aquiles", "J-2417", _AQUILES_TRACE, now - 28 * 60)

    # SDLC · running phase 5 of 9
    upsert_room({
        "name": "sdlc", "role": "coder · ci/release",
        "color": "#c69bff", "track": "coder",
        "presence": "on", "pinned": False, "job_id": "J-2416",
        "state_label": "running · phase 5/9",
    })
    _ingest_trace("sdlc", "J-2416", _SDLC_TRACE, now - 6 * 60)

    # Bob · syncing
    upsert_room({
        "name": "bob", "role": "athena · borrowing",
        "color": "#74d9a2", "track": "athena",
        "presence": "on", "state_label": "syncing · 26%",
    })
    _ingest_trace("bob", None, _BOB_TRACE, now - 8 * 60)

    # Hydra · idle but with FYI
    upsert_room({
        "name": "hydra", "role": "athena · decision",
        "color": "#5cd0c4", "track": "athena",
        "presence": "idle", "state_label": "waiting on PR",
    })
    _ingest_trace("hydra", None, _HYDRA_TRACE, now - 14 * 60)

    # Brandson · idle, delegated work done
    upsert_room({
        "name": "brandson", "role": "git agent",
        "color": "#a78bfa", "track": "git",
        "presence": "idle", "state_label": "branch created · ready",
    })
    _ingest_trace("brandson", "J-2417", _BRANDSON_TRACE, now - 26 * 60)

    # Studio · stale
    upsert_room({
        "name": "studio", "role": "athena · ml store",
        "color": "#ffb059", "track": "athena",
        "presence": "stale", "state_label": "stale · last sync 24h ago",
    })
    _ingest_trace("studio", None, _STUDIO_TRACE, now - 24 * 3600)

    # Light rooms — just metadata + a system "idle" event
    LIGHT = [
        ("jenkins",    "build agent",     "#5cd0c4", "build",  "idle", "all builds green"),
        ("spinnaker",  "deploy agent",    "#74d9a2", "deploy", "idle", "canary 90s green"),
        ("inspector",  "terraform agent", "#ffb059", "infra",  "idle", "no drift"),
        ("confluence", "docs agent",      "#c69bff", "docs",   "idle", "indexed 14m ago"),
        ("jira",       "tickets agent",   "#ff8fb3", "jira",   "idle", "linked CARSN-1287"),
        ("csb",        "athena · syndicate", "#9aa0b3", "athena", "on", "syncing partial · 26%"),
        ("pixie",      "athena · pricing",  "#ff8fb3", "athena", "idle", "all green"),
    ]
    for name, role, color, track, presence, label in LIGHT:
        upsert_room({"name": name, "role": role, "color": color, "track": track,
                     "presence": presence, "state_label": label})
        _ingest_trace(name, None, [{"event_type": "system",
                                    "payload": {"text": label}, "offset": 0}],
                      now - 60 * 60)


def _ingest_trace(room: str, job_id: str | None,
                  events: list[dict], base_ts: float) -> None:
    for ev in events:
        append_event({
            "room": room,
            "job_id": job_id,
            "event_type": ev["event_type"],
            "actor": ev.get("actor"),
            "payload": ev.get("payload", {}),
            "duration_ms": ev.get("duration_ms"),
            "tokens": ev.get("tokens"),
            "ts": base_ts + ev.get("offset", 0),
        })
