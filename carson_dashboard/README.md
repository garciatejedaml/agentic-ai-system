# carson dashboard

Live + historical observability for the Carson agentic AI system.
Runs standalone with a built-in simulator so you can see it work without
Carson connected. Drops into Carson's existing FastAPI app with two lines
of code when you're ready to plug in real data.

---

## run it now (standalone demo)

```bash
cd "Carson AI Copilot for JP Morgan"
pip install -r carson_dashboard/requirements.txt
python -m carson_dashboard
# open http://127.0.0.1:8765/
```

On boot the simulator seeds 240 historical runs across the last 7 days and
starts pushing one new live run every ~8 seconds through the SSE bus.
Reset the data with:

```bash
python -c "from carson_dashboard import db; db.init_db(reset=True)"
```

The SQLite file lives at `$TMPDIR/carson_dashboard.db` by default.
Override with the `CARSON_DB` env var.

---

## what's in the box

```
carson_dashboard/
├── __main__.py            standalone entrypoint (dev only)
├── routes.py              FastAPI router · /dashboard · /api/* · /sse
├── db.py                  SQLite schema + helpers (runs · steps · tool_calls)
├── stream.py              in-memory pub/sub for SSE
├── instrumentation.py     hooks Carson's LangGraph → db + stream
├── simulator.py           fake workloads + seed history
└── static/
    ├── index.html         single-page app shell
    ├── dashboard.css      design tokens + all view styles
    └── dashboard.js       hash router · SSE client · views
```

Three views, hash-routed:

- `#/` · **live** · agent graph + reasoning stream + 60s timeline + status bar
- `#/history` · **history** · time-range stats, agent performance table,
  signals worth investigating, recent runs list
- `#/run/<id>` · **run detail** · hero header, swimlane timeline, full
  reasoning trace with tool calls and tokens per step

---

## integrate into Carson (VDI)

In `carson_service.py` (or wherever your FastAPI app is built):

```python
from carson_dashboard.routes import router as dashboard_router, mount_static
from carson_dashboard import db, instrumentation

db.init_db()                         # creates tables if missing
app.include_router(dashboard_router)
mount_static(app)
graph = instrumentation.wrap_langgraph(graph)   # see below
```

`wrap_langgraph` is a placeholder right now. To capture real Carson runs,
replace its body with a LangChain callback handler that calls
`instrumentation.record_run_start`, `record_step`, `record_run_end`, and
`record_tool_call` at the right lifecycle hooks. The SQL writes plus the
SSE bus are already wired — the dashboard requires no further changes
once those callbacks are firing.

Set `CARSON_DB=/var/lib/carson/dashboard.db` (or wherever you want
persistence on the VDI) before launching.

---

## schema

Three tables, deliberately narrow:

- **runs**: id, started_at, ended_at, status, input_text, user, model,
  total_tokens, cost_usd, meta (JSON)
- **steps**: id, run_id, seq, agent, started_at, ended_at, status,
  summary, reasoning, tokens, latency_ms, meta (JSON)
- **tool_calls**: id, step_id, tool, args (JSON), result (JSON),
  started_at, duration_ms

Anything richer (retries, sub-graphs, branches) goes in the `meta` JSON
columns rather than into new tables. Migrate when there's a real reason.

---

## why these choices

- **Single FastAPI app, not a microservice.** Drops into Carson's
  existing process. Zero new infra.
- **SQLite, not Postgres.** One file on local disk. Carson writes,
  dashboard reads. Survives months of runs without tuning. Swap later if
  you outgrow it.
- **SSE, not WebSocket.** Server → browser only is what we need.
  Trivially debuggable (it's a normal HTTP response with `text/event-stream`).
  Survives proxies that mangle WebSocket upgrades.
- **Vanilla JS, no build step.** No npm, no webpack, no node version
  drama on the VDI. One `cp -r` to ship.
- **Dark-first UI.** The mockups defined the visual language. CSS
  variables auto-flip for light mode if you set
  `<html data-theme="auto">`.

---

## not in this version (intentional cut)

- Run-vs-run comparison view (next)
- Sparklines on the history stat cards (have the data, need the SVG)
- Authentication (assume internal-only behind JPMC SSO on VDI)
- Distributed agents / multi-process Carson (replace stream.py with
  Redis pubsub when needed)
