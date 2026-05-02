# Carson dashboard — full wire-up contract

The dashboard now has **10 tabs**:

```
live · autonomous · chats · pm · ops · cost · replay · autonomy · audit · history
```

The visual + data layers are complete. Most tabs read from `/api/*`
endpoints that already return seeded fixtures. To make it fully alive
against real Carson, Copilot needs to wire **6 behaviour bridges** —
documented below in priority order.

---

## Priority order for the demo

1. **Chat behaviour** (CHAT_WIREUP.md, already shipped) — highest ROI,
   blocks most other "talk to Carson" demos.
2. **Replay timeline** — connect to real run history (already partially
   connected; verify swimlanes render right against real data).
3. **Cost aggregations** — point at production telemetry once available.
4. **Audit log** — wire writes from every state transition.
5. **Multi-chat** — federate the existing single-chat behaviour to
   per-session contexts.
6. **PM agent** — actually create Jira / Confluence on approval.

---

## Bridge 1 — Chat (already documented)

See `CHAT_WIREUP.md`. Same contract applies inside the new
`#/chats` view, just scoped per session.

For multi-chat specifically, the SSE events get a `session_id` field:

```
chat.user_message   { session_id, id, name, text, ts }
chat.routing        { session_id, track, agent, confidence, signals[] }
chat.agent_message  { session_id, agent, text, ts, actions[] }
chat.progress       { session_id, agent, job_id, phase, idx, total, text, ts }
chat.hitl_request   { session_id, agent, job_id, text, actions[], ts }
chat.system         { session_id, text, ts }
```

The frontend filters incoming events by the active `session_id`. Other
sessions get an unread bump on their entry in the left rail.

---

## Bridge 2 — Replay timeline (verify only)

The endpoint `GET /api/replay/{run_id}/timeline` already reads from the
existing `runs / steps / tool_calls` tables and assembles:

```
{
  run_id, title, started_at, ended_at, duration_s, status,
  agents_involved: [...],
  swimlanes: [{agent, segments: [{start, end, status}]}],
  events: [{ts, type, agent, ...}],   # phase_start | phase_end | tool_call
  frame_stream: [{ts_abs, ts_rel, agent, text, status}],
  totals: { tokens, cost_usd },
}
```

To verify against real Carson runs:

```
curl http://127.0.0.1:8765/api/replay/<real_run_id>/timeline
```

If `swimlanes` are empty or `frame_stream` text is generic, it means
the existing runs table doesn't capture enough per-step reasoning. The
fix is in your existing langgraph callback handler (see
`carson_dashboard/instrumentation.py`) — make sure each
`record_step` call has a non-trivial `reasoning` and `summary`.

---

## Bridge 3 — Cost aggregations

Currently `metrics.py` returns mostly seeded fixtures. To wire real:

| metric | source | swap with |
|---|---|---|
| `prs_shipped` | hardcoded 2847 | `SELECT COUNT(*) FROM autonomous_jobs WHERE state='ok'` |
| `hours_saved` | derived | keep formula, drop the `prs_shipped < 50` fallback |
| `dollars_saved` | derived | keep formula |
| `bugs_caught` | hardcoded 47 | `SELECT COUNT(*) FROM ops_events WHERE action='build_fail'` |
| `hitl_under_4min_pct` | hardcoded 0.89 | derive from `audit_log` rows where `event_type='hitl_approve'` and `(ts - created_at) < 240s` |
| `autonomy_trend` | linear interpolation | weekly groupby on autonomous_jobs |
| `leaderboard` | curated fixture | requires adding an `agent` column to `autonomous_jobs` (see "Schema upgrade" below) |

**Schema upgrade for the leaderboard:**

```sql
ALTER TABLE autonomous_jobs ADD COLUMN agent TEXT;
```

Then update `webhooks.receive_jira` to write `agent=cls.agent` when
upserting the job, and the leaderboard query becomes a real GROUP BY.

---

## Bridge 4 — Audit log writes

Every meaningful agent action should call `audit.insert_audit(...)`.
Recommended hook points:

| Carson action | audit row |
|---|---|
| coder agent merges a PR | `event_type='approval'`, `resource='PR #X · repo'`, `approved_by='auto · branch policy'` or `actor` if HITL |
| spinnaker rolls back | `event_type='rollback'`, `resource='svc · env'`, `approved_by='auto · slo breach'` |
| athena agent finishes a sync | `event_type='index_sync'`, `resource='athena.X · N chunks'` |
| user approves HITL via dashboard | `event_type='hitl_approve'`, `resource='J-XXX'`, `approved_by=user_email` |
| any agent reads a credential / scoped data | `event_type='data_access'`, `resource='scope_id · classification'` |
| terraform apply | `event_type='deploy'`, `resource='module · region'`, `approved_by='auto · plan diff'` |

The `metadata` field (free-form JSON) can carry the run_id, the
git SHA, the trace_id from X-Ray, any region/cluster info. Don't put
sensitive values in there.

---

## Bridge 5 — Multi-session chat

The single-chat path (`POST /api/chat/message` from CHAT_WIREUP.md) is
already wired. To federate it across the new sessions:

1. `POST /api/chats/{session_id}/messages` is the new entry point.
2. The handler should look up the session's `agent_focus` and pass it
   as a hint to the router (so an "athena"-focused session prefers
   athena agents, "compliance"-focused prefers audit responses, etc.).
3. All emitted SSE events carry `session_id`. Other sessions ignore.

Per-focus router prompt biases:

| focus | bias |
|---|---|
| athena | prefer knowledge agents (bob, hydra, csb, pixie, studio, sdlc, aquiles) |
| coder | prefer aquiles or sdlc with a job creation |
| compliance | summarize from audit_log instead of running an agent |
| ops | summarize from ops_events instead of running an agent |
| pm | route to pm agent (Bridge 6) |
| general | default — full classifier |

---

## Bridge 6 — PM agent (Jira + Confluence creation)

The `/api/pm/draft/{epic|jira|confluence}` endpoints currently return
**proposals** (the AI's suggested structure). When the user clicks
"approve & create", the dashboard calls a new endpoint:

```
POST /api/pm/commit/epic          { draft, project_id }
POST /api/pm/commit/jira          { draft, parent_epic? }
POST /api/pm/commit/confluence    { draft, space }
```

Each commit endpoint should:
1. Call the real Jira / Confluence API via your existing MCP server
2. Write the new ID back into `pm_epics` / `pm_deliverables` /
   `confluence_pages`
3. Insert an `audit_log` row of type `config_change`
4. Publish a `chat.agent_message` (in the active session) with the URL
   and a "view in Jira" action

Keep the heuristic drafter (`pm.draft_epic`) for offline previews. Wire
Haiku 4.5 / CDAOSDK into it later — same return shape, no UI change.

---

## Hard constraints — read before any change

1. Do NOT modify any file in `carson_dashboard/static/`. The UI is
   locked. All adaptation lives behind the API contract.
2. Do NOT change the response shape of any existing `/api/*` endpoint.
   Add new endpoints; never refactor old ones.
3. Do NOT add new tabs to the dashboard. We have 10. That is the
   ceiling for this release.
4. Each bridge should land in its own PR. Do NOT bundle.
5. Each bridge has a verification checklist (below). All boxes must
   tick before merging.

---

## Verification checklist (per bridge)

### Chat
- [ ] `POST /api/chat/message {text}` → `chat.user_message` + `chat.routing` arrive on /sse
- [ ] An agent run emits `chat.progress` events
- [ ] HITL produces `chat.hitl_request` with the right `actions[]`
- [ ] Action button click maps to `/api/autonomous/jobs/{id}/{action}`

### Replay
- [ ] `/api/replay/<real_run_id>/timeline` returns ≥ 3 swimlanes
- [ ] Frame stream lines have non-trivial reasoning text
- [ ] Tool calls show args (not "no args")

### Cost
- [ ] Counters update without restarting the server (within 60s)
- [ ] Leaderboard reflects real agent activity (new schema column)

### Audit
- [ ] Every PR merge produces a row of `event_type='approval'`
- [ ] Every rollback produces a row of `event_type='rollback'`
- [ ] Filter by type returns only matching rows

### Multi-chat
- [ ] Two sessions open in two browsers stay isolated
- [ ] Unread badges update for the inactive session
- [ ] Pinning a session moves it to the top

### PM
- [ ] Drafting an epic returns a proposal in < 2s
- [ ] Approving a draft creates a real Jira ticket
- [ ] The new ticket appears in the kanban without page refresh
- [ ] An audit row of `config_change` is written

---

## What's intentionally NOT here

- **Auth** — every endpoint is open. Add JWT/SSO at the edge before
  prod. Out of scope for this demo.
- **PDF export** — `/api/audit/export` returns a stub. Wire weasyprint
  or reportlab in a follow-up.
- **Real-time leaderboard** — currently fixture-backed. Bridge 3 makes
  it real.
- **Cross-tab dedup of notifications** — works via the `tag` field on
  `Notification` (already done) but service worker for offline alerts
  is a polish.
- **Mobile** — every view degrades to single-column at narrow widths
  but isn't optimized for touch yet.
