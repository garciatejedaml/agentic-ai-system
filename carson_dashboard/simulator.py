"""Fake Carson workloads so the dashboard demo runs end-to-end.

Drops historical runs into SQLite at startup, then keeps generating new
runs in the background that flow through the SSE bus.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from typing import Iterable

from . import db, instrumentation as inst

AGENTS = [
    ("router",      "cdao sdk"),
    ("Brandson",    "git agent"),
    ("Jenkins",     "build agent"),
    ("Spinnaker",   "deploy agent"),
    ("Inspector",   "terraform agent"),
    ("Confluence",  "docs agent"),
    ("Jira",        "tickets agent"),
]

INTENTS = [
    ("deploy svc-payments {ver} → prod-eu", ["router", "Brandson", "Jenkins", "Spinnaker", "Jira"]),
    ("verify drift on tfstate {region}",    ["router", "Inspector", "Jira"]),
    ("publish release notes for {ver}",     ["router", "Confluence", "Jira"]),
    ("rollback svc-orders to {ver}",        ["router", "Brandson", "Spinnaker", "Jira"]),
    ("audit deps for svc-quotes",           ["router", "Brandson", "Jenkins", "Inspector"]),
    ("sync open tickets to release plan",   ["router", "Jira", "Confluence"]),
]

REGIONS  = ["eu-west-1", "us-east-1", "ap-south-1"]
VERSIONS = [f"v{maj}.{minor}.{patch}"
            for maj in range(1, 4)
            for minor in range(0, 6)
            for patch in range(0, 4)]


def _new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:7]


def _pick_intent() -> tuple[str, list[str]]:
    template, agents = random.choice(INTENTS)
    return (
        template.format(ver=random.choice(VERSIONS), region=random.choice(REGIONS)),
        list(agents),
    )


def _step_summary(agent: str, intent: str) -> tuple[str, str]:
    """Return (summary, reasoning) tailored to the agent."""
    if agent == "router":
        return (
            "Parsed intent · routing to next agent",
            f"Intent classified. Selected workflow path based on '{intent.split()[0]}'.",
        )
    if agent == "Brandson":
        return (
            f"Resolved git tag {random.choice(VERSIONS)} → {uuid.uuid4().hex[:7]}",
            "Working tree clean. Tag matches HEAD on origin/main. Safe to hand off.",
        )
    if agent == "Jenkins":
        return (
            f"Resolved {random.randint(20, 60)} dependencies · running tests",
            "All deps pinned. Triggered mvn test on agent-pool-3.",
        )
    if agent == "Spinnaker":
        return (
            f"Pipeline 'svc-{random.choice(['payments','orders','quotes'])}' running",
            "Canary stage at 25%. Health checks green for 90s.",
        )
    if agent == "Inspector":
        return (
            f"Plan vs apply on {random.choice(REGIONS)} · {random.randint(0,4)} drift",
            "Comparing remote tfstate against local plan. Reviewing security group rules.",
        )
    if agent == "Confluence":
        return (
            "Indexing release notes draft",
            "Pulled changelog from git. Cross-referenced ticket descriptions.",
        )
    if agent == "Jira":
        return (
            f"Linked CARSN-{random.randint(1000, 1999)} to deploy run",
            "Found related epic. Updated status and added deploy run id as comment.",
        )
    return ("Step", "")


def _seed_one_run(end_at: float) -> None:
    """Insert one historical run that finished at end_at."""
    intent, path = _pick_intent()
    run_id = _new_run_id()
    duration = random.uniform(3.0, 22.0)
    started = end_at - duration
    status = random.choices(
        ["ok", "ok", "ok", "ok", "ok", "warn", "error"],
        weights=[6, 6, 6, 6, 6, 2, 1],
    )[0]
    user = random.choice(["martin@jpmc", "alex@jpmc", "sami@jpmc"])
    total_tokens = 0

    db.insert_run({
        "id": run_id,
        "started_at": started,
        "ended_at": end_at,
        "status": status,
        "input_text": intent,
        "user": user,
        "model": "claude-sonnet-4-6",
        "total_tokens": 0,
        "cost_usd": 0.0,
    })

    t = started
    for seq, agent in enumerate(path):
        latency = random.uniform(0.1, 3.5)
        if agent == "Jenkins" and status == "error":
            latency = random.uniform(8, 14)
        tokens = int(latency * random.uniform(800, 1400))
        total_tokens += tokens
        summary, reasoning = _step_summary(agent, intent)
        step_status = "ok"
        if seq == len(path) - 1 and status != "ok":
            step_status = status
        db.insert_step({
            "run_id": run_id,
            "seq": seq,
            "agent": agent,
            "started_at": t,
            "ended_at": t + latency,
            "status": step_status,
            "summary": summary,
            "reasoning": reasoning,
            "tokens": tokens,
            "latency_ms": int(latency * 1000),
        })
        t += latency

    db.update_run(run_id, total_tokens=total_tokens, cost_usd=total_tokens * 1.5e-5)


def seed_history(num_runs: int = 240, span_days: float = 7.0) -> None:
    """Populate the db with historical runs spread across span_days."""
    db.init_db()
    if db.list_runs(limit=1):
        return  # already seeded
    now = time.time()
    span_s = span_days * 86400
    for _ in range(num_runs):
        end_at = now - random.uniform(60, span_s)
        _seed_one_run(end_at)


async def _live_run() -> None:
    """Generate one live run, streaming events through the bus."""
    intent, path = _pick_intent()
    run_id = _new_run_id()
    started = time.time()
    user = random.choice(["martin@jpmc", "alex@jpmc"])
    inst.record_run_start({
        "id": run_id,
        "started_at": started,
        "status": "running",
        "input_text": intent,
        "user": user,
        "model": "claude-sonnet-4-6",
    })

    final_status = random.choices(
        ["ok", "ok", "ok", "ok", "warn", "error"],
        weights=[6, 6, 6, 6, 2, 1],
    )[0]
    total_tokens = 0
    t = started
    seq = 0
    for agent in path:
        seq += 1
        # publish "thinking" first
        thinking_step = {
            "run_id": run_id,
            "seq": seq,
            "agent": agent,
            "started_at": t,
            "ended_at": None,
            "status": "thinking",
            "summary": _step_summary(agent, intent)[0],
            "reasoning": _step_summary(agent, intent)[1],
            "tokens": 0,
            "latency_ms": 0,
        }
        inst.record_step(thinking_step)
        await asyncio.sleep(random.uniform(0.6, 2.0))
        # finalize the step
        latency = time.time() - t
        tokens = int(latency * random.uniform(800, 1400))
        total_tokens += tokens
        step_status = "ok"
        if seq == len(path) and final_status != "ok":
            step_status = final_status
        finalized = {
            **thinking_step,
            "ended_at": time.time(),
            "status": step_status,
            "tokens": tokens,
            "latency_ms": int(latency * 1000),
        }
        inst.record_step(finalized)
        t = time.time()

    inst.record_run_end(run_id, final_status, total_tokens, total_tokens * 1.5e-5)


async def live_loop(interval: float = 6.0) -> None:
    """Background task: generate live runs forever."""
    while True:
        try:
            await _live_run()
        except Exception:
            pass
        await asyncio.sleep(random.uniform(interval * 0.5, interval * 1.5))
