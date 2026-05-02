"""Multi-session chat — the chat panel scaled to N concurrent threads.

Two tables:
  chat_sessions  — one per conversation (left rail in the UI)
  chat_messages  — full history per session

Each session has an `agent_focus` (general | athena | coder | compliance |
ops | pm) which biases the router. The chat itself uses the existing
event contract (chat.user_message, chat.routing, chat.agent_message,
chat.progress, chat.hitl_request) — just scoped per session_id.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .db import _connect, cursor, _row_to_dict


_CHAT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    agent_focus     TEXT NOT NULL DEFAULT 'general',
    owner           TEXT,
    created_at      REAL NOT NULL,
    last_msg_at     REAL,
    last_msg_preview TEXT,
    last_msg_agent  TEXT,
    unread          INTEGER DEFAULT 0,
    pinned          INTEGER DEFAULT 0,
    archived        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    type          TEXT NOT NULL,
    agent         TEXT,
    name          TEXT,
    text          TEXT NOT NULL,
    actions_json  TEXT,
    metadata_json TEXT,
    ts            REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_msg_session ON chat_messages(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_chat_session_last ON chat_sessions(last_msg_at DESC);
"""

FOCUSES = ("general", "athena", "coder", "compliance", "ops", "pm")


def init_chat_db() -> None:
    with cursor() as c:
        c.executescript(_CHAT_SCHEMA)


# ── Sessions ────────────────────────────────────────────────────────────


def create_session(title: str, agent_focus: str = "general",
                   owner: str | None = None) -> dict[str, Any]:
    sid = "ch-" + uuid.uuid4().hex[:8]
    now = time.time()
    with cursor() as c:
        c.execute(
            """INSERT INTO chat_sessions
               (id, title, agent_focus, owner, created_at, last_msg_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, title, agent_focus, owner, now, now),
        )
    return get_session(sid)


def get_session(session_id: str) -> dict[str, Any] | None:
    with _connect() as c:
        row = c.execute(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_sessions(include_archived: bool = False) -> list[dict]:
    q = "SELECT * FROM chat_sessions"
    if not include_archived:
        q += " WHERE archived = 0"
    q += " ORDER BY pinned DESC, last_msg_at DESC NULLS LAST"
    with _connect() as c:
        rows = c.execute(q).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_session(session_id: str, **fields) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k} = :{k}" for k in fields)
    with cursor() as c:
        c.execute(f"UPDATE chat_sessions SET {keys} WHERE id = :id",
                  {**fields, "id": session_id})


def archive_session(session_id: str) -> None:
    update_session(session_id, archived=1)


def pin_session(session_id: str, pinned: bool) -> None:
    update_session(session_id, pinned=1 if pinned else 0)


def mark_read(session_id: str) -> None:
    update_session(session_id, unread=0)


# ── Messages ────────────────────────────────────────────────────────────


def append_message(session_id: str, msg: dict[str, Any]) -> int:
    ts = msg.get("ts") or time.time()
    with cursor() as c:
        cur = c.execute(
            """INSERT INTO chat_messages
               (session_id, type, agent, name, text, actions_json,
                metadata_json, ts)
               VALUES (:session_id, :type, :agent, :name, :text,
                       :actions_json, :metadata_json, :ts)""",
            {
                "session_id": session_id,
                "type": msg["type"],
                "agent": msg.get("agent"),
                "name": msg.get("name"),
                "text": msg["text"],
                "actions_json": json.dumps(msg.get("actions", [])) if msg.get("actions") else None,
                "metadata_json": json.dumps(msg.get("metadata", {})),
                "ts": ts,
            },
        )
        # bump session
        preview = msg["text"][:120]
        c.execute(
            """UPDATE chat_sessions
               SET last_msg_at = ?, last_msg_preview = ?, last_msg_agent = ?
               WHERE id = ?""",
            (ts, preview, msg.get("agent") or msg.get("name"), session_id),
        )
        return cur.lastrowid


def list_messages(session_id: str, limit: int = 200) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? "
            "ORDER BY ts ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        if d.get("actions_json"):
            try: d["actions"] = json.loads(d["actions_json"])
            except Exception: d["actions"] = []
        out.append(d)
    return out
