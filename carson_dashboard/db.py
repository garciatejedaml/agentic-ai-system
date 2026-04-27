"""SQLite layer for the Carson dashboard.

Schema is intentionally narrow: three tables that capture everything the
dashboard needs without coupling to LangGraph internals. Anything richer
(branches, retries, sub-graphs) can be encoded in `meta` JSON columns.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

# Default to a writable temp location for portability across hosts.
# Override with CARSON_DB env var when integrating into a real Carson deploy.
DB_PATH = Path(os.environ.get(
    "CARSON_DB",
    Path(os.environ.get("TMPDIR", "/tmp")) / "carson_dashboard.db",
))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            TEXT PRIMARY KEY,
    started_at    REAL NOT NULL,
    ended_at      REAL,
    status        TEXT NOT NULL,            -- running | ok | warn | error
    input_text    TEXT NOT NULL,
    user          TEXT,
    model         TEXT,
    total_tokens  INTEGER DEFAULT 0,
    cost_usd      REAL DEFAULT 0,
    meta          TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS steps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    agent         TEXT NOT NULL,            -- router | Brandson | Jenkins | ...
    started_at    REAL NOT NULL,
    ended_at      REAL,
    status        TEXT NOT NULL,            -- thinking | ok | warn | error
    summary       TEXT NOT NULL,
    reasoning     TEXT,
    tokens        INTEGER DEFAULT 0,
    latency_ms    INTEGER DEFAULT 0,
    meta          TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id       INTEGER NOT NULL REFERENCES steps(id) ON DELETE CASCADE,
    tool          TEXT NOT NULL,
    args          TEXT,
    result        TEXT,
    started_at    REAL NOT NULL,
    duration_ms   INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_runs_started   ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_steps_run_seq  ON steps(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_tools_step     ON tool_calls(step_id);
"""

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def cursor():
    """Thread-safe write cursor. Reads can use connect() directly."""
    with _lock:
        conn = _connect()
        try:
            yield conn
        finally:
            conn.close()


def init_db(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    with cursor() as c:
        c.executescript(_SCHEMA)


# --- Writes ----------------------------------------------------------------


def insert_run(run: dict[str, Any]) -> None:
    with cursor() as c:
        c.execute(
            """INSERT OR REPLACE INTO runs
               (id, started_at, ended_at, status, input_text, user, model,
                total_tokens, cost_usd, meta)
               VALUES (:id, :started_at, :ended_at, :status, :input_text,
                       :user, :model, :total_tokens, :cost_usd, :meta)""",
            {
                "id": run["id"],
                "started_at": run["started_at"],
                "ended_at": run.get("ended_at"),
                "status": run.get("status", "running"),
                "input_text": run.get("input_text", ""),
                "user": run.get("user"),
                "model": run.get("model"),
                "total_tokens": run.get("total_tokens", 0),
                "cost_usd": run.get("cost_usd", 0.0),
                "meta": json.dumps(run.get("meta", {})),
            },
        )


def update_run(run_id: str, **fields: Any) -> None:
    if not fields:
        return
    if "meta" in fields and not isinstance(fields["meta"], str):
        fields["meta"] = json.dumps(fields["meta"])
    keys = ", ".join(f"{k} = :{k}" for k in fields)
    with cursor() as c:
        c.execute(f"UPDATE runs SET {keys} WHERE id = :id", {**fields, "id": run_id})


def insert_step(step: dict[str, Any]) -> int:
    with cursor() as c:
        cur = c.execute(
            """INSERT INTO steps
               (run_id, seq, agent, started_at, ended_at, status, summary,
                reasoning, tokens, latency_ms, meta)
               VALUES (:run_id, :seq, :agent, :started_at, :ended_at, :status,
                       :summary, :reasoning, :tokens, :latency_ms, :meta)""",
            {
                "run_id": step["run_id"],
                "seq": step["seq"],
                "agent": step["agent"],
                "started_at": step["started_at"],
                "ended_at": step.get("ended_at"),
                "status": step.get("status", "thinking"),
                "summary": step.get("summary", ""),
                "reasoning": step.get("reasoning"),
                "tokens": step.get("tokens", 0),
                "latency_ms": step.get("latency_ms", 0),
                "meta": json.dumps(step.get("meta", {})),
            },
        )
        return cur.lastrowid


def insert_tool_call(call: dict[str, Any]) -> None:
    with cursor() as c:
        c.execute(
            """INSERT INTO tool_calls
               (step_id, tool, args, result, started_at, duration_ms)
               VALUES (:step_id, :tool, :args, :result, :started_at, :duration_ms)""",
            {
                "step_id": call["step_id"],
                "tool": call["tool"],
                "args": json.dumps(call.get("args")) if call.get("args") is not None else None,
                "result": json.dumps(call.get("result")) if call.get("result") is not None else None,
                "started_at": call["started_at"],
                "duration_ms": call.get("duration_ms", 0),
            },
        )


# --- Reads -----------------------------------------------------------------


def list_runs(limit: int = 50, since: float | None = None) -> list[dict]:
    q = "SELECT * FROM runs"
    args: list[Any] = []
    if since is not None:
        q += " WHERE started_at >= ?"
        args.append(since)
    q += " ORDER BY started_at DESC LIMIT ?"
    args.append(limit)
    with _connect() as c:
        rows = c.execute(q, args).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_run(run_id: str) -> dict | None:
    with _connect() as c:
        row = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = _row_to_dict(row)
        steps = c.execute(
            "SELECT * FROM steps WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
        run["steps"] = [_row_to_dict(s) for s in steps]
        for s in run["steps"]:
            tools = c.execute(
                "SELECT * FROM tool_calls WHERE step_id = ?", (s["id"],)
            ).fetchall()
            s["tool_calls"] = [_row_to_dict(t) for t in tools]
    return run


def aggregate_window(seconds: float) -> dict:
    """Aggregate stats across recent runs."""
    cutoff = time.time() - seconds
    with _connect() as c:
        runs = c.execute(
            "SELECT * FROM runs WHERE started_at >= ?", (cutoff,)
        ).fetchall()
    total = len(runs)
    ok = sum(1 for r in runs if r["status"] == "ok")
    durations = [
        (r["ended_at"] - r["started_at"]) for r in runs if r["ended_at"]
    ]
    tokens = sum(r["total_tokens"] or 0 for r in runs)
    return {
        "runs": total,
        "success_rate": (ok / total * 100) if total else 0.0,
        "avg_duration_s": (sum(durations) / len(durations)) if durations else 0.0,
        "total_tokens": tokens,
    }


def agent_stats(seconds: float) -> list[dict]:
    cutoff = time.time() - seconds
    with _connect() as c:
        rows = c.execute(
            """SELECT agent,
                      COUNT(*) AS runs,
                      AVG(latency_ms) AS avg_latency,
                      SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors
               FROM steps
               WHERE started_at >= ?
               GROUP BY agent
               ORDER BY runs DESC""",
            (cutoff,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row | Iterable) -> dict:
    d = dict(row)
    if "meta" in d and isinstance(d["meta"], str):
        try:
            d["meta"] = json.loads(d["meta"])
        except json.JSONDecodeError:
            d["meta"] = {}
    for k in ("args", "result"):
        if k in d and isinstance(d[k], str) and d[k]:
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d
