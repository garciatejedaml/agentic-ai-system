"""Replay / time-travel — reconstruct any past run as a scrubable timeline.

Reads from runs/steps/tool_calls and produces:
  - agents_involved: ordered list
  - swimlanes: per-agent activity segments (start/end relative to run start)
  - events: timestamped event list (phase_start, phase_end, tool_call,
            hitl_request, agent_message)
  - frame_stream: reasoning lines with absolute + relative ts
"""
from __future__ import annotations

import json
import time
from typing import Any

from .db import _connect


def get_timeline(run_id: str) -> dict[str, Any] | None:
    with _connect() as c:
        run = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            return None
        steps = c.execute(
            "SELECT * FROM steps WHERE run_id = ? ORDER BY started_at", (run_id,)
        ).fetchall()
        tools_by_step: dict[int, list] = {}
        for s in steps:
            tcs = c.execute(
                "SELECT * FROM tool_calls WHERE step_id = ? ORDER BY started_at",
                (s["id"],),
            ).fetchall()
            tools_by_step[s["id"]] = [_tc(r) for r in tcs]

    started = run["started_at"]
    ended = run["ended_at"] or time.time()
    duration_s = ended - started

    agents = []
    seen = set()
    for s in steps:
        if s["agent"] not in seen:
            agents.append(s["agent"])
            seen.add(s["agent"])

    swimlanes = {a: [] for a in agents}
    events = []
    frame_stream = []
    for s in steps:
        rel_start = s["started_at"] - started
        rel_end = (s["ended_at"] or s["started_at"]) - started
        swimlanes[s["agent"]].append({
            "start": round(rel_start, 1),
            "end": round(rel_end, 1),
            "status": s["status"],
        })
        events.append({
            "ts": round(rel_start, 1),
            "type": "phase_start",
            "agent": s["agent"],
            "phase": s["summary"][:40] if s["summary"] else "",
            "status": s["status"],
        })
        if s["ended_at"]:
            events.append({
                "ts": round(rel_end, 1),
                "type": "phase_end",
                "agent": s["agent"],
                "status": s["status"],
            })
        for tc in tools_by_step.get(s["id"], []):
            events.append({
                "ts": round(tc["started_at"] - started, 1),
                "type": "tool_call",
                "agent": s["agent"],
                "tool": tc["tool"],
                "args": tc.get("args"),
                "duration_ms": tc.get("duration_ms"),
            })
        frame_stream.append({
            "ts_abs": s["started_at"],
            "ts_rel": round(rel_start, 1),
            "agent": s["agent"],
            "text": s["reasoning"] or s["summary"] or "",
            "status": s["status"],
        })

    events.sort(key=lambda e: e["ts"])

    return {
        "run_id": run_id,
        "title": run["input_text"],
        "user": run["user"],
        "model": run["model"],
        "started_at": started,
        "ended_at": run["ended_at"],
        "duration_s": round(duration_s, 1),
        "status": run["status"],
        "agents_involved": agents,
        "swimlanes": [{"agent": a, "segments": swimlanes[a]} for a in agents],
        "events": events,
        "frame_stream": frame_stream,
        "totals": {
            "tokens": run["total_tokens"] or 0,
            "cost_usd": run["cost_usd"] or 0.0,
        },
    }


def list_recent_runs(limit: int = 20) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT id, started_at, ended_at, status, input_text, total_tokens, cost_usd "
            "FROM runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def _tc(r) -> dict:
    d = dict(r)
    for k in ("args", "result"):
        if k in d and isinstance(d[k], str) and d[k]:
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d
