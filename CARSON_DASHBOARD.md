# Carson Observability Dashboard — Architecture & Implementation

**Document version**: 2.0
**Last updated**: 2026-04-26
**Replaces**: `langgraph-system/carson_agents/templates/dashboard.html` (current 130 KB monolith)
**Companion**: `CARSON_AUDIT_FIXES.md` (fix index FIX #23–#25 references this file)

> **⚠ IMPORTANT: This document describes the target architecture for Carson's dashboard.**
> Carson currently runs **locally on Citrix VDI**. Sections referencing AWS services (DynamoDB, CloudWatch, X-Ray, ECS, ALB, WAF, OpenSearch, multi-region) describe the **planned cloud deployment**, not the current state. The current dashboard is the 130 KB monolith HTML served by FastAPI locally. Do not implement cloud-specific sections until the AWS migration decision is made.

---

## Table of contents

1. [Vision](#vision)
2. [Why a new dashboard](#why-a-new-dashboard)
3. [Architecture overview](#architecture-overview)
4. [Five views](#five-views)
5. [Data flow](#data-flow)
6. [Backend service](#backend-service)
7. [Frontend SPA](#frontend-spa)
8. [Distributed tracing](#distributed-tracing)
9. [Metrics catalog](#metrics-catalog)
10. [Cloud deployment](#cloud-deployment)
11. [SSE and WebSocket transport at scale](#transport-at-scale)
12. [SLOs, alerts, and runbooks](#slos-alerts-runbooks)
13. [Multi-region considerations](#multi-region)
14. [Database schema](#database-schema)
15. [SSE event schema](#sse-event-schema)
16. [API surface](#api-surface)
17. [Implementation file layout](#file-layout)
18. [Integration with Carson](#integration-with-carson)
19. [Migration plan](#migration-plan)
20. [Future roadmap](#future-roadmap)

---

## Vision

The Carson dashboard is the **single pane of glass** for everything happening in the Carson agentic AI system. A user opens it and within 15 seconds knows:

- Is Carson healthy right now?
- What ran in the last hour, on whose behalf, against which tool, with what cost?
- Where is the slow request? The expensive one? The one that failed?
- What's our SLO compliance this month?
- Where in a particular run did a specific agent decide what?

The dashboard is **the operations interface** for Carson. It is not a chat client. It is what an SRE looks at when paged, what a finance person looks at when reviewing cost, what a developer looks at when debugging a routing decision, and what a platform owner looks at when deciding whether to roll out Sonnet 4.

In one phrase: **the dashboard is to Carson what the AWS Console is to AWS** — a complete, real-time, drillable, auditable view of the system's behavior, available 99.9% of the time, with sub-500ms interactive latency.

### Design principles

1. **Push, not poll** — the LLM is never in the dashboard's data path. Metrics push from the in-memory tracker over SSE; CloudWatch is the long-term store.
2. **One source of truth per metric** — `token_tracker` for tokens/cost, X-Ray for traces, DynamoDB for thread state, S3 for cold storage.
3. **No monoliths** — HTML/CSS/JS split into per-concern files. Each file is testable in isolation.
4. **Multi-tenant from day one** — every page filters by team_id (no team can see another team's runs).
5. **Salt Design System native** — the dashboard looks and feels like other JPMC products.
6. **Cloud-native observability** — every metric exported to CloudWatch, every span to X-Ray, every log structured.
7. **Drill-down is one click everywhere** — from "live agent activity" to a specific step's reasoning trace is at most three clicks.
8. **Read-only by default** — the dashboard never mutates Carson state. Actions (cancel a run, retry, etc.) are explicit and confirmed.

---

## Why a new dashboard

The current dashboard (`templates/dashboard.html`, 130 KB) suffers from structural problems documented in `CARSON_AUDIT_FIXES.md`:

| Problem (fix ID) | Impact |
|---|---|
| 130 KB single file (FIX #23) | Every change touches one giant file; no module isolation |
| Polls Bedrock on a timer (FIX #0.3) | Money leak; the dashboard makes LLM calls just to refresh metrics |
| `render_template_string` for static content (FIX #24) | Wasted CPU on every dashboard request |
| Three CSS systems mixed (FIX #25) | Color update requires editing 30+ hex literals |
| `<style>` inside `<body>` | Invalid HTML |
| `onclick=` and `href="javascript:void(0)"` (FIX #29) | Broken keyboard nav, screen reader hostile |
| Charts via `innerHTML` template literals (FIX #30) | XSS-prone, untestable |
| No distributed tracing | Can't follow a request across agents |
| No multi-tenancy | All teams see all data |

The new dashboard described here fixes all of these and adds **enterprise-grade capabilities**: distributed tracing, cost views, alert views, SLO compliance, audit trails, multi-region support, push-based real-time updates.

---

## Architecture overview

### High-level diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Browser (corp user)                         │
│   ┌────────────────────────────────────────────────────────┐        │
│   │  Single-Page App                                        │        │
│   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │        │
│   │  │ Live │ │ Hist │ │ Run  │ │ Cost │ │Alerts│         │        │
│   │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘         │        │
│   │                                                          │        │
│   │  SSE client ←─────────── push events                    │        │
│   │  fetch(/api/*) ←──────── on-demand reads                │        │
│   └────────────────────────────────────────────────────────┘        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTPS
                           ▼
                ┌──────────────────────┐
                │      AWS WAF + ALB    │
                └──────────┬────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────────────┐
        │  ECS Fargate (Carson tasks, multi-AZ)             │
        │                                                    │
        │  FastAPI service                                  │
        │  ├── /dashboard/*           (SPA, static assets)  │
        │  ├── /dashboard/api/*       (read endpoints)      │
        │  ├── /dashboard/sse         (push events)         │
        │  ├── /dashboard/ws          (bidirectional, opt.) │
        │  ├── /api/* (existing routers)                    │
        │  │                                                 │
        │  EventBus (in-process)                            │
        │  ├── publish(event)                               │
        │  └── subscribe() → AsyncIterator                  │
        │                                                    │
        │  TokenTracker (existing, exposed read-only)       │
        │  Instrumentation (LangGraph callbacks)            │
        └──────────┬───────────────────────────────────────┘
                   │
       ┌───────────┼───────────┬─────────────┬──────────────┐
       ▼           ▼           ▼             ▼              ▼
  ┌────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐  ┌────────────┐
  │DynamoDB│ │ Cloud   │ │  X-Ray   │ │   S3     │  │  Carson    │
  │hot path│ │ Watch   │ │  traces  │ │  audit   │  │  (existing │
  │threads │ │ Metrics │ │          │ │  cold    │  │  runtime)  │
  └────────┘ └─────────┘ └──────────┘ └──────────┘  └────────────┘
```

### Components

| Component | Role | New / Existing |
|---|---|---|
| SPA frontend | Live UI for users | New (replaces `dashboard.html`) |
| FastAPI dashboard module | HTTP + SSE + WebSocket endpoints | New |
| EventBus | In-process pub/sub for SSE | New |
| Instrumentation hooks | LangGraph callbacks → events | New |
| Token tracker | Token/cost accumulation | Existing (`token_tracker.py`) |
| DynamoDB hot path | Threads, recent metrics | New (CLD #7 in audit) |
| CloudWatch Metrics | Long-term metrics, dashboards, alarms | New (CLD #5) |
| X-Ray | Distributed traces | New (CLD #6) |
| S3 audit | Compliance audit log | New (CLD #12) |

### Cross-cutting concerns

- **Authentication**: ALB integration with corp SSO. Each user's `user_sid` in JWT claims.
- **Authorization**: dashboard reads filter by `team_id` (from JWT or path); a user only sees their team's data.
- **Observability**: the dashboard itself is instrumented (it's a meta-observability surface). Dashboard requests get their own X-Ray subsegment so we can detect dashboard slowness.

---

## Five views

The dashboard surfaces five primary views, each with a distinct user goal.

### 1. Live view (`#/`)

**Goal**: "what is Carson doing right now?"

**Layout** (top to bottom):

- **Status bar** (1 row): tokens/min, avg latency, active runs, errors in last hour. Numbers in monospace, sub-100ms refresh from the EventBus.
- **Agent graph** (~50% viewport): SVG of the 25 agents in a layout grouped by category (devops_tools / athena_knowledge / autonomous_coding / notifications / observability). Each agent is a node; the router is the central hub. Edges animate when a request flows through. Active agents pulse. Errored agents glow red with a tooltip describing the error.
- **Reasoning stream** (~30% viewport): scrolling log of the last ~80 reasoning lines. Three columns: timestamp, agent name, message. Color-coded by status (`thinking`/`ok`/`warn`/`error`). Click a line to jump to the run detail view.
- **Activity timeline** (60s rolling, ~15% viewport): one row per agent, segments showing when each agent was active. Hover a segment for tooltip with cost/tokens.

**Live data sources**:
- SSE stream from `/dashboard/sse`
- Event types: `run.start`, `run.end`, `step.start`, `step.end`, `tool_call`, `agent.error`

### 2. History view (`#/history`)

**Goal**: "what happened in the last X period?"

**Layout**:

- **Time range pills**: 1h / 24h / 7d / 30d / Custom
- **Aggregate stats** (4 cards with sparklines): runs, avg duration, success rate, tokens used. Each card has a small sparkline showing the metric over the chosen window.
- **Agent performance table**: per-agent breakdown — runs, p50, p95, errors, retry rate, cost. Sortable. Trend arrow per row showing change vs previous period.
- **Signals worth investigating** (right panel): auto-detected anomalies — top error agent, latency regressions, cost spikes, low-confidence routing. Each signal is one or two sentences explaining the anomaly with a "drill in" button.
- **Recent runs list**: paginated table, click a row to open run detail.

**Data sources**:
- `/dashboard/api/stats?window=24h` → DynamoDB metrics + CloudWatch Metric Insights
- `/dashboard/api/runs?since=24h&limit=80` → DynamoDB threads table

### 3. Run detail view (`#/run/<run_id>`)

**Goal**: "what exactly did this run do, and where did it fail?"

**Layout**:

- **Header**: run id, status, duration, tokens, cost, model, tool calls. Plus the input request and the final response.
- **Distributed trace link**: button "Open in X-Ray" (deep link), and an inline trace summary (top 5 spans by duration).
- **Swimlane timeline**: one row per agent that participated. Each step is a segment; segment color indicates status; segment width is duration. Click a segment to scroll to that step in the reasoning trace below.
- **Reasoning trace**: chronological list of every step. Each step shows: agent, timestamp offset, reasoning, tool calls (with arguments and results), tokens, latency. Tool call arguments and responses are folded by default, expandable.
- **Confirmation/HITL banner**: if the run is paused awaiting human approval, a banner at the top with the pending action and an "approve" / "reject" button (subject to authorization).

**Data sources**:
- `/dashboard/api/runs/<run_id>` → DynamoDB + X-Ray
- `/dashboard/api/runs/<run_id>/trace` → X-Ray detail

### 4. Cost view (`#/cost`)

**Goal**: "how much is Carson costing us, by what dimensions?"

**Layout**:

- **Total cost YTD / month / week / day** — big numbers.
- **Cost trend chart** — daily cost over selected window with breakdown by model.
- **Cost by agent** — bar chart, descending. Click a bar to drill into runs that drove the cost.
- **Cost by intent category** — devops_tools / athena_knowledge / etc.
- **Top expensive runs** — table of last 50 runs sorted by cost, with quick links to run detail.
- **Token efficiency**: cached vs raw input tokens. Shows the savings from prompt caching.
- **Forecast**: linear projection of monthly cost based on last 7 days.

**Data sources**:
- CloudWatch Metric Insights (Carson/${team}/EstimatedCostUsd)
- `/dashboard/api/cost/by_agent`
- `/dashboard/api/cost/by_intent`
- `/dashboard/api/cost/top_runs?limit=50`

### 5. Alerts view (`#/alerts`)

**Goal**: "what is wrong, and what was wrong recently?"

**Layout**:

- **Active alarms**: live list of CloudWatch alarms in `ALARM` state, with last transition time and runbook link.
- **Alarm history**: timeline of last 7 days of state transitions.
- **SLO compliance**: per-SLO badge — green/amber/red — with current value vs target. Click a badge for SLO detail (window, error budget remaining, latest breaches).
- **Synthetic check status**: a small panel showing the result of the synthetic canary running every 5 minutes against a known query.
- **PagerDuty / OpsGenie integration**: links to the on-call schedule and to recent incidents.

**Data sources**:
- CloudWatch Alarms API
- CloudWatch Synthetics
- PagerDuty API (optional)

---

## Data flow

### Live mode

```
Carson agent run starts
        │
        ▼
LangGraph instrumentation hook  ─┐
        │                         │
        ▼                         ▼
   token_tracker.record()    EventBus.publish("step", {...})
        │                         │
        ▼                         ▼
   In-memory store         SSE → all subscribed browsers
        │                         │
        ▼                         ▼
   CloudWatchExporter         Browser DOM update (~50ms)
   pushes every 60s
        │
        ▼
   CloudWatch Metrics
        │
        ▼
   Long-term storage + alarms
```

### History mode

```
Browser opens #/history?window=24h
        │
        ▼
fetch /dashboard/api/stats?window=24h
        │
        ▼
FastAPI handler
   ├── DynamoDB Query (carson-${team}-metrics)
   ├── CloudWatch Metric Insights query (90-day archive)
   └── Compose unified response
        │
        ▼
JSON to browser
        │
        ▼
Render stats cards, table, signals
```

### Run detail mode

```
Browser opens #/run/abc123
        │
        ▼
fetch /dashboard/api/runs/abc123
        │
        ▼
FastAPI handler
   ├── DynamoDB GetItem (threads table)
   ├── X-Ray GetTraceSummary (trace_id from thread record)
   └── S3 HeadObject (audit log presence)
        │
        ▼
JSON: { run, steps, tool_calls, trace_summary, audit_records }
        │
        ▼
Render header, swimlanes, trace
```

---

## Backend service

### Module structure

```
langgraph-system/carson_agents/dashboard/
├── __init__.py
├── routes.py                  FastAPI router
├── stream.py                  EventBus (in-process pub/sub)
├── instrumentation.py         LangGraph callbacks → events + DDB writes
├── repository.py              Read-side: DynamoDB + CloudWatch + X-Ray queries
├── projector.py               Hot-path metrics aggregation (in-process)
├── auth.py                    JWT validation, team scoping
├── signals.py                 Anomaly detection for "signals" panel
└── static/
    ├── index.html             ~5 KB shell only
    ├── dashboard.css          ~30 KB, Salt-aligned
    └── dashboard.js           ~50 KB modular SPA
```

### `routes.py` (FastAPI router)

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from pathlib import Path

from .auth import current_user, require_team_access
from .stream import bus, serialize
from .repository import (
    list_runs, get_run, get_stats, get_cost_breakdown,
    get_active_alarms, get_slo_compliance,
)
from .signals import compute_signals

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
STATIC_DIR = Path(__file__).parent / "static"


@dashboard_router.get("/", include_in_schema=False)
async def shell():
    return FileResponse(STATIC_DIR / "index.html")


@dashboard_router.get("/api/health")
async def health():
    return {"ok": True, "listeners": bus.listener_count}


@dashboard_router.get("/api/runs")
async def api_runs(
    window: str = "24h",
    limit: int = 80,
    user=Depends(current_user),
):
    return await list_runs(team_id=user.team_id, window=window, limit=limit)


@dashboard_router.get("/api/runs/{run_id}")
async def api_run_detail(run_id: str, user=Depends(current_user)):
    run = await get_run(team_id=user.team_id, run_id=run_id)
    if not run:
        raise HTTPException(404, f"run {run_id} not found")
    require_team_access(user, run["team_id"])
    return run


@dashboard_router.get("/api/stats")
async def api_stats(window: str = "24h", user=Depends(current_user)):
    stats = await get_stats(team_id=user.team_id, window=window)
    runs = await list_runs(team_id=user.team_id, window=window, limit=200)
    stats["signals"] = compute_signals(stats, runs)
    return stats


@dashboard_router.get("/api/cost/by_agent")
async def api_cost_by_agent(window: str = "30d", user=Depends(current_user)):
    return await get_cost_breakdown(
        team_id=user.team_id, window=window, dimension="agent",
    )


@dashboard_router.get("/api/cost/top_runs")
async def api_cost_top_runs(window: str = "7d", limit: int = 50, user=Depends(current_user)):
    return await list_runs(
        team_id=user.team_id, window=window, limit=limit,
        order_by="cost_usd", desc=True,
    )


@dashboard_router.get("/api/alerts")
async def api_alerts(user=Depends(current_user)):
    return {
        "active":  await get_active_alarms(team_id=user.team_id),
        "slos":    await get_slo_compliance(team_id=user.team_id),
    }


@dashboard_router.get("/sse")
async def sse_stream(user=Depends(current_user)):
    """Server-Sent Events for live updates. Filtered by team_id."""

    async def gen():
        async for event in bus.subscribe():
            if event.get("team_id") != user.team_id:
                continue
            yield {
                "event": event.get("type", "message"),
                "data":  serialize(event),
            }

    return EventSourceResponse(gen())


def mount_static(app):
    """Call once after include_router."""
    app.mount(
        "/dashboard/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="dashboard_static",
    )
```

### `stream.py` (EventBus)

```python
import asyncio, json, time
from typing import AsyncIterator

class EventBus:
    """In-process pub/sub. Multi-process: replace with Redis pubsub or SNS+SQS fanout."""

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    def publish(self, event: dict) -> None:
        event = {"ts": time.time(), **event}
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncIterator[dict]:
        q = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)

    @property
    def listener_count(self) -> int:
        return len(self._subscribers)


bus = EventBus()


def serialize(event: dict) -> str:
    return json.dumps(event, default=str)
```

### `instrumentation.py` (LangGraph callbacks → events)

```python
import time, uuid
from typing import Any
from .stream import bus
from .repository import write_run_start, write_run_end, write_step

def record_run_start(team_id: str, run: dict[str, Any]) -> None:
    """Persist + announce a new run."""
    run.setdefault("id", "run_" + uuid.uuid4().hex[:7])
    run["team_id"] = team_id
    run["started_at"] = run.get("started_at", time.time())
    write_run_start(run)                         # DynamoDB
    bus.publish({"type": "run.start", "team_id": team_id, "run": run})


def record_run_end(team_id: str, run_id: str, status: str,
                   total_tokens: int = 0, cost_usd: float = 0.0) -> None:
    write_run_end(team_id, run_id, status, total_tokens, cost_usd)
    bus.publish({
        "type": "run.end",
        "team_id": team_id,
        "run_id": run_id,
        "status": status,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
    })


def record_step(team_id: str, step: dict[str, Any]) -> int:
    step_id = write_step(team_id, step)
    bus.publish({"type": "step", "team_id": team_id, "step_id": step_id, **step})
    return step_id


def wrap_langgraph(graph, team_id: str):
    """Attach instrumentation as a LangGraph callback."""
    from langchain_core.callbacks import BaseCallbackHandler

    class CarsonCallback(BaseCallbackHandler):
        def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None,
                            tags=None, metadata=None, **kwargs):
            # Map LangGraph chain start to our event model
            record_run_start(team_id, {
                "id": str(run_id),
                "input_text": str(inputs.get("user_request", "")),
                "user_sid": metadata.get("user_sid") if metadata else None,
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
            })

        def on_chain_end(self, outputs, *, run_id, **kwargs):
            record_run_end(team_id, str(run_id), status="ok",
                           total_tokens=outputs.get("total_tokens", 0),
                           cost_usd=outputs.get("cost_usd", 0.0))

        def on_chain_error(self, error, *, run_id, **kwargs):
            record_run_end(team_id, str(run_id), status="error")

        def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
            # ... emit tool_call event ...
            pass

    return graph.with_config(callbacks=[CarsonCallback()])
```

### `repository.py` (read side, DynamoDB + CloudWatch)

```python
import boto3
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key

ddb = boto3.resource("dynamodb")
cw = boto3.client("cloudwatch")
xray = boto3.client("xray")


def _threads_table(team_id: str):
    return ddb.Table(f"carson-{team_id}-threads")


def _metrics_table(team_id: str):
    return ddb.Table(f"carson-{team_id}-metrics")


async def list_runs(team_id, window="24h", limit=80, order_by="updated_at", desc=True):
    table = _threads_table(team_id)
    cutoff = _window_to_unix(window)
    resp = table.query(
        IndexName="by_user_recent",
        KeyConditionExpression=Key("user_sid").eq("*") & Key("updated_at").gte(cutoff),
        Limit=limit,
        ScanIndexForward=not desc,
    )
    return resp["Items"]


async def get_run(team_id, run_id):
    table = _threads_table(team_id)
    # ... query by thread_id ...
    pass


async def get_stats(team_id, window="24h"):
    """Aggregate stats from CloudWatch Metric Insights for performance."""
    cutoff = datetime.utcnow() - _window_delta(window)

    response = cw.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "tokens",
                "Expression": f"SELECT SUM(InputTokens) FROM SCHEMA(\"Carson/{team_id}\", Agent) GROUP BY Agent",
                "Period": _window_to_period(window),
            },
            {
                "Id": "cost",
                "Expression": f"SELECT SUM(EstimatedCostUsd) FROM \"Carson/{team_id}\"",
                "Period": _window_to_period(window),
            },
            {
                "Id": "latency_p95",
                "Expression": f"SELECT PERCENTILE(AvgLatencyMs, 95) FROM \"Carson/{team_id}\" GROUP BY Agent",
                "Period": _window_to_period(window),
            },
        ],
        StartTime=cutoff,
        EndTime=datetime.utcnow(),
    )

    return _format_stats(response)


async def get_cost_breakdown(team_id, window, dimension):
    """Cost grouped by dimension (agent, intent, model)."""
    # CloudWatch Metric Insights query grouped by dimension
    pass


async def get_active_alarms(team_id):
    resp = cw.describe_alarms(
        AlarmNamePrefix=f"carson-{team_id}-",
        StateValue="ALARM",
    )
    return resp["MetricAlarms"]


async def get_slo_compliance(team_id):
    # Query CloudWatch Metric Insights for SLI math
    pass


def write_run_start(run: dict):
    """Idempotent insert of a new run record."""
    table = _threads_table(run["team_id"])
    table.put_item(
        Item={**run, "updated_at": int(run["started_at"])},
        ConditionExpression="attribute_not_exists(thread_id)",
    )


def write_run_end(team_id, run_id, status, total_tokens, cost_usd):
    table = _threads_table(team_id)
    table.update_item(
        Key={"user_sid": "*", "thread_id": run_id},
        UpdateExpression="SET #s=:s, ended_at=:e, total_tokens=:t, cost_usd=:c, updated_at=:u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": status, ":e": int(time.time()), ":t": total_tokens,
            ":c": cost_usd, ":u": int(time.time()),
        },
    )


def write_step(team_id, step: dict) -> int:
    """Persist a step. Returns step seq number."""
    table = _threads_table(team_id)
    # ... append to steps list on the run record ...
    pass
```

### `signals.py` (anomaly detection)

```python
def compute_signals(stats: dict, runs: list[dict]) -> list[dict]:
    """Heuristic 'things worth investigating' for the history view."""
    out = []

    # Top error agent
    by_agent = stats.get("by_agent", [])
    worst = max(by_agent, key=lambda a: a.get("errors", 0), default=None)
    if worst and worst.get("errors", 0) > 0:
        out.append({
            "kind":  "regress",
            "category": worst["agent"],
            "text": f"{worst['errors']} step error(s) in window. {worst['agent']} is the top error contributor — drill in.",
            "drill_in": f"#/history?agent={worst['agent']}&status=error",
        })

    # Slowest agent vs threshold
    slow = max(by_agent, key=lambda a: a.get("avg_latency_ms", 0), default=None)
    if slow and slow.get("avg_latency_ms", 0) > 5000:
        out.append({
            "kind": "warn",
            "category": slow["agent"],
            "text": f"{slow['agent']} averaging {slow['avg_latency_ms']/1000:.1f}s/step. Above 5s threshold.",
            "drill_in": f"#/history?agent={slow['agent']}",
        })

    # Cost spike
    aggregate = stats.get("aggregate", {})
    if aggregate.get("cost_usd_today", 0) > 1.5 * aggregate.get("cost_usd_avg_7d", 0):
        out.append({
            "kind": "regress",
            "category": "cost",
            "text": f"Today's cost ${aggregate['cost_usd_today']:.2f} is >150% of 7-day average. Investigate.",
            "drill_in": "#/cost?window=24h",
        })

    # Failure rate
    failed = [r for r in runs if r.get("status") == "error"]
    if runs and len(failed) / len(runs) > 0.05:
        out.append({
            "kind": "regress",
            "category": "reliability",
            "text": f"{len(failed)}/{len(runs)} runs failed ({len(failed)/len(runs)*100:.1f}%). Above 5% threshold.",
            "drill_in": "#/history?status=error",
        })

    return out
```

### `auth.py` (JWT + team scoping)

```python
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel
import jwt

class User(BaseModel):
    sid: str
    team_id: str
    roles: list[str]

async def current_user(authorization: str = Header(...)) -> User:
    """Validate the bearer token from the corp SSO JWT."""
    try:
        token = authorization.removeprefix("Bearer ")
        claims = jwt.decode(token, key=PUBLIC_KEY, algorithms=["RS256"], audience="carson")
        return User(
            sid=claims["sub"],
            team_id=claims.get("team_id", "ahtw"),  # default for back-compat
            roles=claims.get("roles", []),
        )
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")


def require_team_access(user: User, target_team_id: str):
    if user.team_id != target_team_id and "carson_admin" not in user.roles:
        raise HTTPException(403, "Cross-team access denied")
```

---

## Frontend SPA

### File structure

```
static/
├── index.html              ~5 KB — shell, includes templates for views
├── dashboard.css           ~30 KB — Salt-aligned, theme-aware
├── dashboard.js            ~50 KB — SPA router, SSE client, view renderers
├── modules/
│   ├── router.js           Hash-based router
│   ├── sse.js              EventSource wrapper with reconnect
│   ├── api.js              Wrapped fetch with auth header
│   ├── views/
│   │   ├── live.js
│   │   ├── history.js
│   │   ├── run.js
│   │   ├── cost.js
│   │   └── alerts.js
│   ├── components/
│   │   ├── agent_graph.js  SVG agent layout
│   │   ├── timeline.js     Swimlane timeline
│   │   ├── stats_card.js   KPI cards with sparklines
│   │   └── reasoning_log.js
│   └── lib/
│       ├── format.js       Date/number formatting
│       └── colors.js       Salt token mapping for status colors
└── vendor/                  (only if CDN is blocked in target env)
    └── salt-ds.js
```

### `index.html`

```html
<!DOCTYPE html>
<html lang="en" data-theme="auto">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Carson · agent dashboard</title>
  <link rel="stylesheet" href="/dashboard/static/dashboard.css" />
</head>
<body>

<header class="topbar">
  <div class="brand">
    <span class="brand-mark"></span>
    <span class="brand-name">carson</span>
    <span class="brand-sub" id="env-tag">prod · ahtw</span>
  </div>
  <nav class="tabs" role="tablist">
    <a href="#/"        data-tab="live">live</a>
    <a href="#/history" data-tab="history">history</a>
    <a href="#/cost"    data-tab="cost">cost</a>
    <a href="#/alerts"  data-tab="alerts">alerts</a>
  </nav>
  <div class="topright">
    <span class="conn"><span class="conn-dot"></span><span id="conn-text">connecting</span></span>
  </div>
</header>

<main id="view" role="main"></main>

<!-- View templates inline so they ship with the shell, no extra fetch -->
<template id="tpl-live">      ... </template>
<template id="tpl-history">   ... </template>
<template id="tpl-run">       ... </template>
<template id="tpl-cost">      ... </template>
<template id="tpl-alerts">    ... </template>

<script type="module" src="/dashboard/static/dashboard.js"></script>
</body>
</html>
```

### `dashboard.js` (main bootstrap)

```javascript
import { initRouter } from './modules/router.js';
import { connectSSE } from './modules/sse.js';

window.addEventListener('load', async () => {
  initRouter();              // hash router
  await connectSSE();        // /dashboard/sse
});
```

### `modules/router.js`

```javascript
import { renderLive }    from './views/live.js';
import { renderHistory } from './views/history.js';
import { renderRun }     from './views/run.js';
import { renderCost }    from './views/cost.js';
import { renderAlerts }  from './views/alerts.js';

export function initRouter() {
  window.addEventListener('hashchange', route);
  route();
}

function route() {
  const hash = location.hash || '#/';
  const [, ...parts] = hash.split('/');
  const view = parts[0];

  setActiveTab(view || 'live');

  switch (view) {
    case '':         return renderLive();
    case 'history':  return renderHistory(new URLSearchParams(location.hash.split('?')[1] || ''));
    case 'run':      return renderRun(parts[1]);
    case 'cost':     return renderCost();
    case 'alerts':   return renderAlerts();
    default:         return renderLive();
  }
}

function setActiveTab(name) {
  document.querySelectorAll('.tabs a').forEach(a => {
    a.classList.toggle('on', a.dataset.tab === name);
  });
}
```

### `modules/sse.js`

```javascript
let es = null;
let backoff = 1000;

const subscribers = new Map(); // event_type → Set<callback>

export function on(eventType, callback) {
  if (!subscribers.has(eventType)) subscribers.set(eventType, new Set());
  subscribers.get(eventType).add(callback);
}

export function off(eventType, callback) {
  subscribers.get(eventType)?.delete(callback);
}

export async function connectSSE() {
  const conn = document.querySelector('.conn');
  conn.classList.remove('on', 'err');
  document.getElementById('conn-text').textContent = 'connecting';

  if (es) try { es.close(); } catch {}

  es = new EventSource('/dashboard/sse', { withCredentials: true });

  es.onopen = () => {
    backoff = 1000;
    conn.classList.add('on');
    document.getElementById('conn-text').textContent = 'live';
  };

  es.onerror = () => {
    conn.classList.remove('on');
    conn.classList.add('err');
    document.getElementById('conn-text').textContent = 'reconnecting';
    setTimeout(() => connectSSE(), backoff);
    backoff = Math.min(backoff * 2, 30_000);  // exponential backoff up to 30s
  };

  ['run.start', 'run.end', 'step', 'tool_call', 'agent.error'].forEach(evt => {
    es.addEventListener(evt, e => {
      const data = JSON.parse(e.data);
      subscribers.get(evt)?.forEach(cb => cb(data));
    });
  });
}
```

### `modules/views/live.js` (sketch)

```javascript
import { on, off } from '../sse.js';
import { renderAgentGraph, updateAgentStatus, animateEdge } from '../components/agent_graph.js';
import { renderTimeline, addTimelineSegment } from '../components/timeline.js';
import { appendReasoningLog } from '../components/reasoning_log.js';
import { renderStats } from '../components/stats_card.js';

const state = {
  agentStatus: {},        // agent_id → 'idle' | 'thinking' | 'ok' | 'warn' | 'error'
  runs: new Set(),        // active run ids
  recentSteps: [],        // last 60s
};

let listeners = [];

export function renderLive() {
  cleanup();

  const view = document.getElementById('view');
  view.replaceChildren(document.getElementById('tpl-live').content.cloneNode(true));

  renderAgentGraph(document.getElementById('agent-graph'));
  renderTimeline(document.getElementById('timeline'));
  renderStats(document.querySelectorAll('.stat'));

  // Subscribe to live events
  const onStep = (step) => {
    state.agentStatus[step.agent] = step.status;
    updateAgentStatus(step.agent, step.status);
    if (step.agent !== 'router') animateEdge('router', step.agent, step.status);

    appendReasoningLog({
      time:   formatTime(step.started_at),
      agent:  step.agent,
      message: step.summary,
      status: step.status,
    });

    if (step.ended_at) {
      addTimelineSegment(step.agent, step.started_at, step.ended_at, step.status);
      state.recentSteps.push(step);
    }
  };

  on('step', onStep);
  listeners.push(['step', onStep]);

  // ... similar handlers for run.start, run.end, agent.error ...
}

function cleanup() {
  listeners.forEach(([evt, cb]) => off(evt, cb));
  listeners = [];
}
```

### CSS — Salt Design System aligned

```css
/* dashboard.css */
:root {
  --salt-brand-primary:        #2670A9;
  --salt-brand-primary-strong: #1A4D7A;
  --salt-status-positive:      #248748;
  --salt-status-negative:      #D32F2F;
  --salt-status-warning:       #E68619;
  --salt-status-info:          #2670A9;

  --bg-0: #0a0a0a;
  --bg-1: #131313;
  --bg-2: #1a1a1a;
  --bg-3: #232323;
  --tx-0: #e6e6e6;
  --tx-1: #a8a8a8;
  --tx-2: #6e6e6e;
  --bd-0: rgba(255,255,255,0.06);
  --bd-1: rgba(255,255,255,0.12);

  --font-mono: ui-monospace, "JetBrains Mono", Menlo, monospace;
  --font-sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
}

@media (prefers-color-scheme: light) {
  :root[data-theme="auto"] {
    --bg-0: #fafaf9;
    --bg-1: #ffffff;
    --tx-0: #1a1a1a;
    --tx-1: #555;
    --tx-2: #888;
  }
}

/* status colors derived from Salt */
.status-ok    { color: var(--salt-status-positive); }
.status-warn  { color: var(--salt-status-warning); }
.status-error { color: var(--salt-status-negative); }
.status-info  { color: var(--salt-status-info); }

/* ... full ~30 KB of styles in modular sections: layout, panels,
       agent graph nodes/edges, timeline, log lines, run detail
       swimlanes, alerts list, etc. ... */
```

---

## Distributed tracing

### Why X-Ray + OpenTelemetry

X-Ray is the AWS-native trace backend with deep ECS integration. OpenTelemetry is the vendor-neutral instrumentation API. Using OTel SDK with the X-Ray exporter gives:

- ECS service map for free (Carson → Bedrock, Carson → DynamoDB, etc.)
- Per-request trace summaries searchable by `service.namespace=ahtw` and `agent.id=jira`
- Sampling controlled at the SDK level (don't trace 100% of requests in prod, sample 10% + always-on for errors)
- Future portability: same instrumentation can export to Datadog, Honeycomb, Jaeger if the team migrates.

### Span hierarchy for one Carson request

```
carson.request                          (root span — created at ALB)
  ├── dashboard.read                    (if dashboard request)
  │
  ├── carson.run                        (a complete agent run)
  │   ├── carson.planner
  │   ├── carson.router
  │   ├── carson.agent.git              (one per invoked agent)
  │   │   ├── llm.bedrock.invoke        (Bedrock call)
  │   │   ├── tool.bitbucket.create_pr  (MCP tool call)
  │   │   └── tool.bitbucket.get_branches
  │   ├── carson.critic
  │   ├── carson.agent.git (retry)      (if critic requested retry)
  │   └── carson.synthesizer
  │
  ├── persistence.write                 (DynamoDB write)
  └── audit.write                       (S3 audit record)
```

Each span has:

- Standard OTel attributes (`service.name`, `service.namespace`, `service.version`)
- Carson-specific attributes (`carson.agent.id`, `carson.intent`, `carson.user_sid`, `carson.session_id`, `carson.tokens_in`, `carson.tokens_out`, `carson.cost_usd`)
- Status code (`OK` / `ERROR`) with error message on failures

### Linking trace ↔ dashboard ↔ logs

Every dashboard run-detail view embeds the X-Ray trace ID. The "Open in X-Ray" button deep-links to the AWS console with the trace pre-loaded. CloudWatch logs are queryable by trace ID:

```
fields @timestamp, @message
| filter trace_id = "1-65a1234-abcdef..."
| sort @timestamp asc
```

The audit S3 records also include `trace_id` so a compliance query for "what did Carson do under this trace_id" returns logs + spans + audit records.

### Sampling policy

- 100% trace error responses (we always want to know about failures)
- 100% trace HITL approvals (compliance requirement)
- 100% trace autonomous coding runs (high-risk capability)
- 10% trace successful normal runs (cost control)
- 0% trace dashboard reads in prod (would 10x our trace volume; sample at 1% if debugging)

Configured via `OTEL_TRACES_SAMPLER` and a custom `SamplerByCondition`:

```python
class CarsonSampler(Sampler):
    def should_sample(self, parent_context, trace_id, name, kind, attributes, *args):
        # Always trace errors and high-risk operations
        if attributes.get("carson.agent.id") == "coder":
            return SamplingResult(Decision.RECORD_AND_SAMPLE)
        if attributes.get("hitl_required"):
            return SamplingResult(Decision.RECORD_AND_SAMPLE)
        # Sample successful normal runs at 10%
        if name.startswith("carson.run"):
            return self._ratio_sampler.should_sample(...)
        # Skip dashboard reads
        if name.startswith("dashboard."):
            return SamplingResult(Decision.DROP)
        return self._default.should_sample(...)
```

---

## Metrics catalog

### CloudWatch namespace: `Carson/${team_id}`

Every metric is dimensioned by at least `Team`. Most are also dimensioned by `Agent`.

#### Token + cost metrics (from `token_tracker`)

| Metric | Unit | Dimensions | Aggregation |
|---|---|---|---|
| `InputTokens`        | None | Team, Agent       | Sum |
| `OutputTokens`       | None | Team, Agent       | Sum |
| `CachedTokens`       | None | Team, Agent       | Sum |
| `EstimatedCostUsd`   | None | Team, Agent       | Sum |
| `RequestCount`       | None | Team, Agent       | Sum |
| `AvgLatencyMs`       | Milliseconds | Team, Agent | Average |

#### Workflow metrics

| Metric | Unit | Dimensions | Aggregation |
|---|---|---|---|
| `WorkflowStartCount`     | None | Team, IntentCategory | Sum |
| `WorkflowSuccessCount`   | None | Team, IntentCategory | Sum |
| `WorkflowErrorCount`     | None | Team, IntentCategory | Sum |
| `WorkflowDurationMs`     | Milliseconds | Team, IntentCategory | p50, p95, p99 |
| `WorkflowCycleDetected`  | None | Team       | Sum |
| `CritiqueRetryCount`     | None | Team, Agent | Sum |
| `CritiqueStagnationCount`| None | Team, Agent | Sum |
| `RoutingConfidence`      | None | Team, Agent | Average, p10 |
| `RoutingLatencyMs`       | Milliseconds | Team       | p50, p95 |
| `ToolCallCount`          | None | Team, Agent, Tool | Sum |
| `ToolCallDurationMs`     | Milliseconds | Team, Agent, Tool | p50, p95 |
| `ToolCallErrorCount`     | None | Team, Agent, Tool | Sum |

#### Dashboard metrics (self-observability)

| Metric | Unit | Dimensions | Aggregation |
|---|---|---|---|
| `DashboardRequests`        | None | Team, Endpoint | Sum |
| `DashboardLatencyMs`       | Milliseconds | Team, Endpoint | p50, p95 |
| `DashboardSseConnections`  | None | Team       | Average |
| `DashboardSseEventsPushed` | None | Team       | Sum |

### CloudWatch dashboard widgets (per team)

Defined in Terraform (`infra/modules/carson/cloudwatch_dashboard.tf`):

```hcl
resource "aws_cloudwatch_dashboard" "carson" {
  dashboard_name = "carson-${var.team_id}"
  dashboard_body = jsonencode({
    widgets = [
      # Row 1: top-level KPIs
      _stat_widget("Total cost (last 24h)",   "EstimatedCostUsd",   "Sum",   86400),
      _stat_widget("Avg latency p95",         "WorkflowDurationMs", "p95",   3600),
      _stat_widget("Success rate",            "WorkflowSuccessCount/WorkflowStartCount", "Average", 3600),
      _stat_widget("Loop detections (24h)",   "WorkflowCycleDetected", "Sum", 86400),

      # Row 2: cost trends
      _line_widget("Cost USD by agent (24h)", "EstimatedCostUsd", group_by="Agent"),

      # Row 3: latency
      _line_widget("p95 latency by agent",    "AvgLatencyMs", stat="p95", group_by="Agent"),

      # Row 4: routing health
      _line_widget("Routing confidence (avg)", "RoutingConfidence", stat="Average"),
      _line_widget("Critic retry count",       "CritiqueRetryCount", stat="Sum"),

      # Row 5: errors
      _line_widget("Errors per agent",         "WorkflowErrorCount", stat="Sum", group_by="Agent"),
    ]
  })
}
```

### Optional: Grafana for richer dashboards

Some teams prefer Grafana over CloudWatch. Grafana managed service can read from CloudWatch directly. The same metrics surface, but with:

- Variable-driven dashboards (team_id, agent, time range as Grafana variables)
- Alerting via Grafana Cloud (alternative to CloudWatch alarms)
- Side-by-side comparisons (this week vs last week)

Grafana dashboards as JSON live in `infra/grafana/` and are provisioned via Terraform's Grafana provider.

---

## Cloud deployment

> **⚠ FUTURE STATE.** This section describes the planned AWS deployment. Carson currently runs locally on Citrix VDI.

### Where the dashboard runs

The dashboard module is **part of the Carson FastAPI service** — same container image, same ECS task. Reasons:

1. SSE needs sticky-ish connections; co-location with the EventBus avoids cross-process pub/sub.
2. Dashboard auth shares JWT validation logic with the rest of the service.
3. One service to deploy, monitor, and scale.

When SSE traffic outgrows in-process pub/sub (probably > 200 simultaneous dashboard tabs per task), split into a dedicated dashboard service backed by Redis pub/sub or AWS SNS+SQS fanout. Until then, the simple architecture wins.

### ALB routing

```
Path                          Backend
─────────────────────────────────────
/dashboard/*                  Carson task (sticky session for SSE)
/dashboard/sse                Carson task (sticky, longer timeout)
/api/*                        Carson task (any)
/health                       Carson task (any)
```

ALB target group for `/dashboard/sse` has `stickiness.lb_cookie.enabled = true` and a longer idle timeout (configured at ALB level: `idle_timeout = 3600` to allow long-lived SSE).

### Auto-scaling considerations for SSE

Each open SSE connection holds a connection slot. ECS Fargate task scaling on CPU alone misses this — a task with 200 idle SSE clients but 5% CPU should still trigger scale-out if approaching connection limits.

Custom metric: `DashboardSseConnections` per task. Auto-scaling target: 100 connections per task. Mirror in Terraform:

```hcl
resource "aws_appautoscaling_policy" "sse_connections" {
  name               = "${local.name}-sse-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.carson.resource_id
  scalable_dimension = aws_appautoscaling_target.carson.scalable_dimension
  service_namespace  = aws_appautoscaling_target.carson.service_namespace

  target_tracking_scaling_policy_configuration {
    customized_metric_specification {
      metric_name = "DashboardSseConnections"
      namespace   = "Carson/${var.team_id}"
      statistic   = "Average"
    }
    target_value       = 100.0
    scale_out_cooldown = 30
    scale_in_cooldown  = 600   # don't scale in too fast — disconnects users
  }
}
```

### Secure access

The dashboard sits behind the same ALB + WAF as the main service:

- ALB requires TLS 1.3.
- WAF rate-limits per IP (1000/5min) — generous enough for active users, blocks scrapers.
- ALB authenticates via OIDC against corp IdP (Okta or equivalent).
- All `/dashboard/*` routes additionally check JWT in `Authorization: Bearer ...` header (validated in `auth.py`).
- `team_id` from JWT claim drives all data filtering — no path parameter-based team selection (cannot be tampered with).

### Multi-tenant isolation

Per-team isolation is enforced at three layers:

1. **JWT claim** — `team_id` is set by IdP, signed, immutable in transit.
2. **Repository layer** — every read query takes `team_id` and queries only that team's DynamoDB table or CloudWatch namespace.
3. **SSE filter** — events are tagged with `team_id` at publish time; `subscribe()` filters by user's `team_id`.

A user from team A cannot see team B's dashboard data even if they craft URLs pointing at team B's IDs.

---

## SSE and WebSocket transport at scale

### Why SSE first

For the live view, all data flow is server-to-client. SSE has:

- Native browser support, no library needed
- Plain HTTP, plays nicely with ALB and WAF
- Easy debugging (open the URL in curl, see the stream)
- Auto-reconnect via `EventSource`

### When to add WebSocket

If we want bidirectional flows in the dashboard — e.g., approving a HITL request from the dashboard, or a user typing into a "ask Carson" prompt embedded in the dashboard — WebSocket is the right channel.

```python
# routes.py
from fastapi import WebSocket

@dashboard_router.websocket("/ws")
async def ws_handler(websocket: WebSocket):
    await websocket.accept()
    user = await authenticate_ws(websocket)

    async for message in websocket.iter_json():
        if message["type"] == "approve_hitl":
            await approve_hitl(user, message["run_id"])
            await websocket.send_json({"ok": True})
        elif message["type"] == "submit_request":
            run_id = await submit_carson_request(user, message["request"])
            await websocket.send_json({"run_id": run_id})
```

ALB supports WebSockets natively, no extra config.

### Scaling beyond one process

When `bus.listener_count` regularly exceeds ~200 per task, split into:

```
Browser (SSE) ─► ALB ─► ECS task (dashboard subset)
                            │
                            ▼
                       Redis (ElastiCache)
                            │
                            ▼
                       SUBSCRIBE channel:team_${team_id}
```

Carson agent processes publish to Redis; dashboard tasks subscribe by team. Now any number of dashboard tasks can scale independently.

For massive fanout (10K+ simultaneous tabs), use **AWS SNS** for fan-out + **HTTP/2 SSE** with each Fargate task subscribing to a per-team SNS topic via SQS.

Trade-off: Redis introduces a new dependency; only adopt when in-process bus hits limits.

---

## SLOs, alerts, and runbooks

(Full SLO and alert table is in `CARSON_AUDIT_FIXES.md` § "SLOs, SLIs, and alerting". Dashboard-specific SLOs below.)

### Dashboard-specific SLOs

| SLO | Target | Window | SLI |
|---|---|---|---|
| Shell load time | p95 < 1s | 30 days | First contentful paint |
| API read latency | p95 < 500ms | 30 days | `/dashboard/api/*` p95 |
| SSE delivery latency | p95 < 2s end-to-end | 30 days | Time from `bus.publish` to browser DOM update |
| SSE connection availability | 99.9% | 30 days | `(1 - sse_drop_rate) over 30d` |
| Run-detail correctness | 100% | n/a | If `/api/runs/<id>` returns the run, all fields are present (no partial results) |

### Synthetic checks

CloudWatch Synthetics canary running every 5 minutes from us-east-1:

```python
# synthetics/dashboard_canary.py
def handler(event, context):
    """Synthetic: open dashboard, fetch live data, verify response."""

    # Step 1: GET /dashboard/ → expect 200 + HTML
    resp = http.get(f"{DASHBOARD_URL}/dashboard/")
    assert resp.status == 200
    assert "<title>Carson" in resp.body

    # Step 2: GET /dashboard/api/health → expect {"ok": true}
    resp = http.get(f"{DASHBOARD_URL}/dashboard/api/health",
                    headers={"Authorization": f"Bearer {SYNTH_JWT}"})
    assert resp.json["ok"] is True

    # Step 3: GET /dashboard/api/runs?limit=1 → expect array
    resp = http.get(f"{DASHBOARD_URL}/dashboard/api/runs?limit=1",
                    headers={"Authorization": f"Bearer {SYNTH_JWT}"})
    assert isinstance(resp.json, list)

    # Step 4: SSE handshake — open EventSource, expect first event within 10s
    es = open_sse(f"{DASHBOARD_URL}/dashboard/sse",
                  headers={"Authorization": f"Bearer {SYNTH_JWT}"})
    first_event = es.next(timeout=10)
    assert first_event is not None
    es.close()

    return {"status": "OK"}
```

Failure of the canary triggers a CloudWatch alarm → SNS → PagerDuty.

### Runbooks

> **Planned — not yet written.** These runbooks will be created as part of the cloud deployment. They do not exist on disk yet.

Stored in `docs/runbooks/`:

- `RUNBOOK_dashboard_5xx.md` — the dashboard returns 5xx. Check ECS task health, ALB target group, recent deployments.
- `RUNBOOK_sse_drops.md` — clients disconnecting frequently. Check ALB idle timeout, ECS task CPU, Redis pubsub if applicable.
- `RUNBOOK_metrics_lag.md` — dashboard shows stale metrics. Check CloudWatchExporter thread health, IAM perms for PutMetricData.
- `RUNBOOK_run_not_found.md` — clicking a run in history returns 404. Check DynamoDB capacity, partition by `team_id`/`user_sid`, recent table modifications.

---

## Multi-region considerations

> **⚠ FUTURE STATE.** Multi-region applies only after cloud migration is complete. Not applicable to the current local setup.

### Active-active read, single-region write

For Phase 6 (multi-region DR), the dashboard read path can be active-active:

```
                                 ┌─── ALB (us-east-1) ─── Dashboard tasks
Browser ──► Route 53 ──┤
                                 └─── ALB (us-west-2) ─── Dashboard tasks (read replica)

                          DynamoDB Global Tables (active-active)
                          CloudWatch metrics in both regions (replicated via cross-account)
                          X-Ray traces stored per-region; unified view via X-Ray groups
                          ChromaDB on S3 with CRR
```

Writes (LangGraph agent runs that modify state) only happen in us-east-1. Reads happen in either region. Route 53 latency-based routing sends users to the nearest region.

### Failover sequence (RTO < 1h)

1. **Detect**: us-east-1 ALB health check fails for 3 consecutive checks.
2. **Route 53 health check** marks us-east-1 unhealthy; DNS flips to us-west-2.
3. **DynamoDB Global Table** is already replicating; us-west-2 promotes to write region (via runbook).
4. **Bedrock** in us-west-2 is independent; CDAOSDK token may need refresh in the new region.
5. **Run detail** for runs that started in us-east-1 may be temporarily inconsistent (DynamoDB Global Table eventual consistency window: ~1s).

### What does not flip automatically

- ChromaDB writes (RAG ingestion) are paused during failover.
- Audit log writes are queued in SQS until us-east-1 recovers; replay on recovery.
- Critic retries in flight at failover time fail and are reported as errors.

---

## Database schema

### DynamoDB: `carson-${team_id}-threads`

Partition key: `user_sid` (String)
Sort key: `thread_id` (String, format `run_<7hex>`)

Attributes:

```
{
  "user_sid":          "SID12345",
  "thread_id":         "run_abc1234",
  "team_id":           "ahtw",
  "intent":            "deploy",
  "intent_category":   "devops_tools",
  "user_request":      "Deploy svc-payments to UAT",
  "started_at":        1745678901,
  "ended_at":          1745678920,
  "updated_at":        1745678920,
  "status":            "ok",                  // running | ok | warn | error
  "model":             "anthropic.claude-3-5-sonnet-20241022-v2:0",
  "total_input_tokens":  12480,
  "total_output_tokens": 1842,
  "total_cached_tokens": 8910,
  "cost_usd":          0.0398,
  "trace_id":          "1-65a1234-abcdef...",
  "steps": [
    {
      "seq": 1,
      "agent": "router",
      "started_at": 1745678901,
      "ended_at":   1745678902,
      "status":     "ok",
      "summary":    "Routed to deploy",
      "reasoning":  "Action verb 'deploy' matched action_patterns.deploy",
      "tokens_in":  340,
      "tokens_out": 22,
      "latency_ms": 142,
      "tool_calls": []
    },
    {
      "seq": 2,
      "agent": "deploy",
      "started_at": 1745678902,
      "ended_at":   1745678920,
      "status":     "ok",
      "summary":    "Deployed svc-payments to UAT successfully",
      "reasoning":  "Triggered Spinnaker pipeline 'svc-payments-uat'",
      "tokens_in":  4280,
      "tokens_out": 612,
      "latency_ms": 18120,
      "tool_calls": [
        {
          "name":     "trigger_pipeline",
          "args":     {"pipeline": "svc-payments-uat"},
          "result":   {"status": "RUNNING", "execution_id": "01J..."},
          "duration_ms": 1240
        }
      ]
    }
  ],
  "expires_at":        1748270920    // 30-day TTL
}
```

GSIs:
- `by_user_recent`: hash=user_sid, range=updated_at — for "my recent runs" queries
- `by_intent`: hash=intent, range=updated_at — for filtered history
- `by_status`: hash=status, range=updated_at — for "all errors" queries

### DynamoDB: `carson-${team_id}-metrics`

Partition key: `team_agent` (composite, e.g. `ahtw#jira`)
Sort key: `minute` (Number, YYYYMMDDHHMM as int)

Attributes:

```
{
  "team_agent":         "ahtw#jira",
  "minute":             202604261430,
  "input_tokens":       12480,
  "output_tokens":      1842,
  "cached_tokens":      8910,
  "cost_usd":           0.0398,
  "request_count":      8,
  "p95_latency_ms":     2120,
  "expires_at":         1748270920    // 7-day TTL
}
```

The CloudWatchExporter writes here in addition to PutMetricData, giving the dashboard a fast hot-path read for the last 7 days without going to CloudWatch (which has metric-extraction latency).

### S3: `carson-audit-${team_id}`

Versioned, Object Lock in compliance mode, 7-year retention, KMS-encrypted.

Object key format:

```
YYYY/MM/DD/<uuid>.json
```

Each object is one audit record (see `CARSON_AUDIT_FIXES.md` CLD #12 schema).

### S3: `carson-kb-${team_id}`

ChromaDB snapshots and "latest" backup.

```
chroma/
├── latest/
│   └── carson_kb.tar.gz
└── snapshots/
    ├── 2026-04-26T18-00-00/
    │   └── carson_kb.tar.gz
    ├── 2026-04-26T12-00-00/
    │   └── carson_kb.tar.gz
    └── ...
```

Lifecycle: snapshots → IA after 30d, Glacier IR after 90d, expire after 365d.

---

## SSE event schema

Every event has these required fields:

```json
{
  "type":     "step",
  "ts":       1745678920.123,
  "team_id":  "ahtw"
}
```

### Event types

#### `run.start`

```json
{
  "type":     "run.start",
  "ts":       1745678901.0,
  "team_id":  "ahtw",
  "run": {
    "id":              "run_abc1234",
    "user_sid":        "SID12345",
    "intent":          "deploy",
    "intent_category": "devops_tools",
    "input_text":      "Deploy svc-payments to UAT",
    "started_at":      1745678901.0,
    "trace_id":        "1-65a1234-abcdef..."
  }
}
```

#### `run.end`

```json
{
  "type":          "run.end",
  "ts":            1745678920.0,
  "team_id":       "ahtw",
  "run_id":        "run_abc1234",
  "status":        "ok",
  "total_tokens":  14322,
  "cost_usd":      0.0398,
  "duration_ms":   19000
}
```

#### `step` (start or end)

```json
{
  "type":         "step",
  "ts":           1745678920.0,
  "team_id":      "ahtw",
  "run_id":       "run_abc1234",
  "step_id":      42,
  "seq":          2,
  "agent":        "deploy",
  "started_at":   1745678902.0,
  "ended_at":     1745678920.0,
  "status":       "ok",
  "summary":      "Deployed svc-payments to UAT successfully",
  "reasoning":    "...",
  "tokens":       4892,
  "latency_ms":   18120,
  "tool_calls":   [...]
}
```

#### `tool_call`

```json
{
  "type":         "tool_call",
  "ts":           1745678910.0,
  "team_id":      "ahtw",
  "run_id":       "run_abc1234",
  "step_id":      42,
  "tool":         "trigger_pipeline",
  "args":         {"pipeline": "svc-payments-uat"},
  "result_summary": "{\"status\": \"RUNNING\"}",
  "duration_ms":  1240,
  "status":       "ok"
}
```

#### `agent.error`

```json
{
  "type":         "agent.error",
  "ts":           1745678920.0,
  "team_id":      "ahtw",
  "run_id":       "run_abc1234",
  "agent":        "deploy",
  "error_type":   "TokenExpiredError",
  "error_message": "Bedrock token expired (refreshing...)",
  "trace_id":     "1-65a1234-..."
}
```

#### `alarm.transition`

```json
{
  "type":         "alarm.transition",
  "ts":           1745678920.0,
  "team_id":      "ahtw",
  "alarm_name":   "carson-ahtw-cost-spike",
  "from_state":   "OK",
  "to_state":     "ALARM",
  "reason":       "Cost exceeded $10/hour for 5 minutes"
}
```

---

## API surface

(All paths are under `/dashboard`. All require valid JWT.)

### Read

```
GET  /                         Dashboard SPA shell (HTML)
GET  /static/dashboard.css     CSS (cacheable)
GET  /static/dashboard.js      JS (cacheable)
GET  /api/health               { ok: bool, listeners: int }
GET  /api/runs                 List runs filtered by window/limit
GET  /api/runs/{run_id}        Run detail with steps
GET  /api/runs/{run_id}/trace  X-Ray trace summary
GET  /api/stats                Aggregate stats + by-agent breakdown
GET  /api/cost/by_agent        Cost breakdown by agent
GET  /api/cost/by_intent       Cost breakdown by intent category
GET  /api/cost/top_runs        Most expensive runs
GET  /api/alerts               Active alarms + SLO compliance
GET  /sse                      Server-Sent Events stream (filtered by team)
```

### Write (mutations from the dashboard)

```
POST /api/runs/{run_id}/cancel       Cancel an in-flight run (requires authz)
POST /api/runs/{run_id}/retry        Retry a failed run
POST /api/hitl/{run_id}/approve      Approve a pending HITL action
POST /api/hitl/{run_id}/reject       Reject a pending HITL action
WS   /ws                             Bidirectional channel for chat-like flows
```

All mutations are audited via `audit.write` (see `CARSON_AUDIT_FIXES.md` CLD #12).

### OpenAPI docs

FastAPI auto-generates `/docs` (Swagger UI) and `/redoc`. The dashboard's API surface is fully documented and discoverable. New endpoints automatically appear in the docs without manual maintenance.

---

## File layout

Final repo structure for the dashboard module:

```
high-touch-agent-prompts/
├── langgraph-system/
│   └── carson_agents/
│       └── dashboard/
│           ├── __init__.py
│           ├── routes.py
│           ├── stream.py
│           ├── instrumentation.py
│           ├── repository.py
│           ├── projector.py
│           ├── auth.py
│           ├── signals.py
│           ├── tests/
│           │   ├── test_routes.py
│           │   ├── test_repository.py
│           │   ├── test_signals.py
│           │   └── conftest.py
│           └── static/
│               ├── index.html
│               ├── dashboard.css
│               ├── dashboard.js
│               └── modules/
│                   ├── router.js
│                   ├── sse.js
│                   ├── api.js
│                   ├── views/
│                   │   ├── live.js
│                   │   ├── history.js
│                   │   ├── run.js
│                   │   ├── cost.js
│                   │   └── alerts.js
│                   └── components/
│                       ├── agent_graph.js
│                       ├── timeline.js
│                       ├── stats_card.js
│                       └── reasoning_log.js
└── infra/
    └── modules/
        └── observability/
            ├── cloudwatch_dashboard.tf
            ├── cloudwatch_alarms.tf
            ├── synthetics.tf
            └── grafana_dashboard.tf
```

---

## Integration with Carson

### Three-line integration in `carson_service.py`

```python
from carson_agents.dashboard.routes import dashboard_router, mount_static
from carson_agents.dashboard.instrumentation import wrap_langgraph

app.include_router(dashboard_router)
mount_static(app)
graph = wrap_langgraph(graph, team_id=config["team_id"])
```

### Where instrumentation hooks fire

```
LangGraph node entry            ─► instrumentation.record_step (status="thinking")
LangGraph node exit             ─► instrumentation.record_step (status="ok"|"warn"|"error")
LangGraph workflow start        ─► instrumentation.record_run_start
LangGraph workflow end          ─► instrumentation.record_run_end
Tool call within agent          ─► instrumentation.record_tool_call
```

Each fires:
1. A write to DynamoDB (`carson-${team}-threads`)
2. A publish to the in-process EventBus (for SSE)
3. A CloudWatch metric update via the exporter (every 60s batch)
4. An X-Ray span (created via OpenTelemetry SDK)
5. (For write actions only) An S3 audit record

### Backwards compatibility during migration

While the migration from the old monolith dashboard is in flight, both dashboards coexist:

- Old dashboard at `/dashboard.legacy` (current `dashboard.html` served by `dashboard.py`)
- New dashboard at `/dashboard`

After 2 weeks of dogfooding, retire `/dashboard.legacy`.

---

## Migration plan

### Step 1 — Deploy new dashboard alongside old (week 1)

- Drop the new `dashboard/` module into `carson_agents/`.
- Add 3-line integration in `carson_service.py`.
- Old `dashboard.py` blueprint serves at `/dashboard.legacy`.
- New `dashboard_router` serves at `/dashboard`.
- Smoke test both work.

### Step 2 — Wire up data sources (week 2)

- Implement `CloudWatchExporter` that reads `token_tracker` → CloudWatch (FIX #0.3 + CLD #5).
- Implement `LangGraph callback` that writes to DynamoDB + EventBus.
- Backfill recent runs from `carson_data/(SID)/threads/*.json` into DynamoDB.

### Step 3 — Dogfood for 2 weeks (weeks 3-4)

- Team uses both dashboards in parallel.
- Compare counts, latencies, costs between the two.
- Fix discrepancies — usually the new one is more accurate (because it reads from the canonical token_tracker, not from re-doing LLM calls).

### Step 4 — Switch defaults (week 5)

- VSCode extension's `carson.openDashboard` now opens new dashboard.
- Old dashboard remains accessible at `/dashboard.legacy` with a deprecation banner.

### Step 5 — Retire old dashboard (week 6+)

- Remove `dashboard.py` blueprint and `templates/dashboard.html`.
- Remove `/dashboard.legacy` route.
- Update docs.

### Step 6 — Cloud migration (weeks 7-13)

- Deploy Carson on AWS ECS Fargate (CLD #1, #2).
- DynamoDB + S3 fully replace `carson_data/` git sync (CLD #7 + FIX #0.6).
- CloudWatch + X-Ray as primary observability backends.
- Dashboard is multi-tenant, multi-AZ, auto-scaling.

---

## Future roadmap

### Near-term (Q3 2026)

1. **Comparison view** (run vs run): pick two runs, see swimlanes side by side and reasoning diff. Useful for "this run worked, that one failed, what differed?"
2. **Sparklines on stat cards**: add inline sparklines on every stat card showing 24h trend. Already designed in mockups; ship it.
3. **Cost forecast**: replace current linear forecast with a simple Holt-Winters seasonal forecast (anticipates Mon-Fri morning peaks).
4. **Routing accuracy view**: surface low-confidence routing decisions (FIX #16) as a paginated list with one-click "Was this routing correct?" feedback to retrain.

### Mid-term (Q4 2026)

5. **Multi-team unified view** (Carson admin only): cross-team aggregate metrics for platform owners. Per-team breakdown of cost, errors, adoption.
6. **Session replay**: export an entire run as a self-contained HTML "trace" file viewable offline. Useful for incident write-ups.
7. **Inline approve from email**: HITL emails (FIX #5) include a one-click approval URL that pre-authenticates and lands on the dashboard's run detail with the approve button highlighted.
8. **Mobile-responsive refresh**: the current design is desktop-first. Add a mobile view focused on alerts + cost + recent runs.

### Long-term (2027+)

9. **AI-assisted dashboard**: an "ask Carson about Carson" chat in the dashboard. "Why was yesterday's cost 30% higher than the day before?" → Carson investigates and explains.
10. **Per-user views**: each user sees their own runs first, with team aggregates below. Adoption metric: % of users who open the dashboard daily.
11. **Federated dashboards**: when many teams adopt Carson, a top-level dashboard at the org level shows total cost, top users, top failing agents — useful for platform owners and finance.
12. **Real-time collaboration**: multiple users on the same run-detail view see each other's cursors / annotations. Useful for incident reviews.

### What's deliberately NOT planned

- **Mutating Carson's prompts from the dashboard**: prompts live in `.agent.md` files, version-controlled. Editing them via the dashboard would create a parallel source of truth — bad pattern.
- **Running queries from the dashboard**: there's already a chat surface (VSCode extension `carson.openChat`). The dashboard is for ops, not chat.
- **Exposing the dashboard publicly**: it's an internal corp tool. Even multi-region DR keeps it inside the corp VPC.

---

## Final notes

This document is meant to be **the long-term architectural reference** for the Carson dashboard. It evolves with the system. Update version at top (currently 2.0) when:

- A new view is added (minor bump: 2.0 → 2.1)
- A breaking schema change happens (major bump: 2.0 → 3.0)
- A new metric is added to the catalog (patch bump: 2.0 → 2.0.1)

The dashboard is **the user-facing surface of all the platform-level work** in `CARSON_AUDIT_FIXES.md`. If a fix lands and isn't visible in the dashboard, it's incomplete. The dashboard makes Carson's behavior accountable.

End of document.
