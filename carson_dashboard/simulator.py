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

from . import db, instrumentation as inst, ops_db, webhooks

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


# ─── Ops simulator (jira / jenkins / spinnaker / pr) ────────────────────────

JIRA_FIXTURES = [
    {"key": "CRED-2418", "summary": "Refresh BOB knowledge index after schema bump",
     "description": "BOB needs to be reindexed against the new credit-decision schema.",
     "project": "CRED", "labels": ["athena", "knowledge"], "repo": "athena-bob"},
    {"key": "CRED-2419", "summary": "Add risk score field to /api/risk endpoint",
     "description": "Add a new field 'tier_score' to the risk endpoint response.",
     "project": "CRED", "labels": ["backend"], "repo": "payments-svc"},
    {"key": "CRED-2420", "summary": "Re-sync HYDRA after schema change",
     "description": "HYDRA fell behind after the credit-decision migration.",
     "project": "CRED", "labels": ["athena"], "repo": "athena-hydra"},
    {"key": "CRED-2421", "summary": "Patch validation in payments-svc",
     "description": "Validation regex broken for IBAN edge cases.",
     "project": "CRED", "labels": ["bug"], "repo": "payments-svc"},
    {"key": "CRED-2422", "summary": "Update terraform-aws-eks to v19",
     "description": "Bump module version + fix provider locks.",
     "project": "INF", "labels": ["infra", "terraform"], "repo": "infra-eks"},
    {"key": "CRED-2423", "summary": "Update credit-tech runbook with new alerts",
     "description": "Confluence runbook needs the new SLO burn alerts documented.",
     "project": "CRED", "labels": ["docs"], "repo": "runbooks"},
    {"key": "CRED-2424", "summary": "Reindex Pixie pricing tier vectors",
     "description": "Pixie pricing collection has stale embeddings after the Q2 catalog update.",
     "project": "CRED", "labels": ["athena"], "repo": "athena-pixie"},
    {"key": "CRED-2425", "summary": "Fix flaky test in order-pricing service",
     "description": "test_apply_discount intermittently fails on CI.",
     "project": "CRED", "labels": ["bug"], "repo": "order-pricing"},
]

OPS_SVCS = ["payments-svc", "risk-engine", "credit-models", "order-pricing",
            "athena-bob", "athena-hydra", "athena-pixie"]
TEAMS = ["credit-tech", "risk-platform", "athena-core", "payments"]


def seed_ops_history() -> None:
    """Populate jira_tickets and ops_events tables on first boot."""
    ops_db.init_ops_db()
    if ops_db.list_tickets(limit=1):
        return  # already seeded

    # Backdate tickets across the last hour
    now = time.time()
    for i, fx in enumerate(JIRA_FIXTURES):
        payload = {**fx}
        # space tickets out so list view looks natural
        recv = now - random.uniform(60, 3600)
        try:
            res = webhooks.receive_jira(payload)
            # rewrite received_at via direct upsert so older items appear older
            ops_db.upsert_ticket({
                "key": payload["key"],
                "project": payload.get("project"),
                "summary": payload.get("summary"),
                "description": payload.get("description"),
                "repo": payload.get("repo"),
                "labels": payload.get("labels", []),
                "received_at": recv,
                "classified_at": recv,
                "track": res["track"],
                "agent": res["agent"],
                "confidence": res["confidence"],
                "signals": res["signals"],
                "backend": res["backend"],
                "job_id": res["job_id"],
            })
        except Exception:
            pass

    # Backfill ops events
    for _ in range(40):
        ev = _make_ops_event()
        ev["received_at"] = now - random.uniform(60, 3600)
        ops_db.insert_ops_event(ev)


def _make_ops_event() -> dict:
    source = random.choices(["jenkins", "spinnaker", "github"], weights=[5, 4, 6])[0]
    target = random.choice(OPS_SVCS)
    team = random.choice(TEAMS)

    if source == "jenkins":
        action = random.choices(
            ["build_ok", "build_ok", "build_ok", "build_started", "build_fail"],
            weights=[5, 5, 5, 2, 1],
        )[0]
        n = random.randint(100, 5000)
        detail = f"{target} · #{n}"
        status = {"build_ok": "ok", "build_started": "run", "build_fail": "fail"}[action]
    elif source == "spinnaker":
        action = random.choices(
            ["deploy_ok", "deploy_started", "deploy_ok", "rolled_back"],
            weights=[4, 3, 4, 1],
        )[0]
        env = random.choice(["staging", "prod-1", "prod-2", "uat"])
        detail = f"{target} · {env}"
        status = {"deploy_ok": "ok", "deploy_started": "run", "rolled_back": "fail"}[action]
    else:  # github
        action = random.choices(
            ["pr_opened", "pr_merged", "review_requested", "pr_merged"],
            weights=[3, 4, 3, 4],
        )[0]
        n = random.randint(100, 999)
        actor = random.choice(["aquiles", "sdlc", "m.koch", "j.smith", "a.patel"])
        detail = f"PR #{n} · {target} · {actor}"
        status = {"pr_opened": "run", "pr_merged": "merged", "review_requested": "run"}[action]

    return {"source": source, "action": action, "target": target,
            "detail": detail, "status": status, "team": team}


async def ops_live_loop(interval: float = 5.0) -> None:
    """Background: keep the ops feed flowing. Mix of new ops events
    and the occasional fresh Jira ticket / HITL ask."""
    while True:
        try:
            roll = random.random()
            if roll < 0.78:
                # new ops event
                ev = _make_ops_event()
                if ev["source"] == "jenkins":
                    payload = {"name": ev["target"], "team": ev["team"],
                               "build": {"number": random.randint(100, 5000),
                                         "phase": "started" if ev["action"] == "build_started" else "completed",
                                         "status": "success" if ev["status"] == "ok" else "failure"}}
                    webhooks.receive_jenkins(payload)
                elif ev["source"] == "spinnaker":
                    payload = {"application": ev["target"], "team": ev["team"],
                               "environment": ev["detail"].split(" · ")[-1],
                               "status": {"deploy_ok": "succeeded",
                                          "deploy_started": "started",
                                          "rolled_back": "rollback"}.get(ev["action"], "started")}
                    webhooks.receive_spinnaker(payload)
                else:
                    payload = {"action": {"pr_opened": "opened",
                                          "pr_merged": "closed",
                                          "review_requested": "review_requested"}.get(ev["action"], "opened"),
                               "pull_request": {"number": random.randint(100, 999),
                                                "merged": ev["action"] == "pr_merged"},
                               "repository": {"name": ev["target"]},
                               "team": ev["team"],
                               "sender": {"login": random.choice(["aquiles", "sdlc", "m.koch"])}}
                    webhooks.receive_github(payload)
            elif roll < 0.92:
                # new jira ticket
                fx = random.choice(JIRA_FIXTURES)
                # Mutate summary/key so each emit is unique-ish
                payload = {**fx, "key": f"CRED-{random.randint(2500, 2999)}"}
                webhooks.receive_jira(payload)
            else:
                # HITL request
                webhooks.request_hitl(
                    job_id=f"J-{uuid.uuid4().hex[:5].upper()}",
                    summary=f"{random.choice(['coder·aquiles','coder·sdlc'])} staged a PR",
                )
        except Exception:
            pass
        await asyncio.sleep(random.uniform(interval * 0.6, interval * 1.4))
