# Carson · the master instruction

This is the **only document Copilot should read end-to-end before
touching any code**. It supersedes CHAT_WIREUP.md and the
CARSON_FULL_WIREUP.md sections — they are kept as architectural
reference.

The dashboard at `carson_dashboard/` ships with **10 working tabs**.
The visual + data layers are complete. This document is how Copilot
adapts the **real Carson runtime** so that the dashboard's behavioural
hooks light up.

---

## §0. Pre-flight check (run this first)

Before any change, verify the repo is in a clean known state:

```bash
cd C:\repos\high-touch-agent-prompts
git status                         # must be clean or only logs
git log -1                          # note the SHA — this is your rollback target
python -m carson_dashboard          # must boot cleanly to localhost:8765
```

Open `http://127.0.0.1:8765/dashboard` in Chrome. Confirm:

- [ ] All 10 tabs render
- [ ] No 404s in the python log
- [ ] At least 4 jobs visible on `#/autonomous`
- [ ] At least 6 sessions on `#/chats`
- [ ] At least 200 audit rows on `#/audit`

If any of those fail, **stop**. Run:

```bash
git checkout HEAD -- carson_dashboard/
git pull origin claude/carson-audit-2026-04-27
```

…to re-sync from the canonical branch. Then re-run pre-flight.

---

## §1. The 6 bridges — priority order

Apply them in this exact order. Each is a separate PR. Do not bundle.

| # | bridge       | what it does                                  | risk |
|---|--------------|------------------------------------------------|------|
| 1 | CHAT         | wire user input → langgraph; agents reply     | low  |
| 2 | REPLAY       | verify timeline endpoint works on real runs   | none |
| 3 | COST         | replace fixture aggregations with real queries | low  |
| 4 | AUDIT        | log writes from every state transition         | low  |
| 5 | MULTI_CHAT   | federate the chat path per session_id          | med  |
| 6 | PM           | commit drafts to real Jira / Confluence        | high |

**Do not touch a higher-numbered bridge before merging the previous
one.** Higher-numbered bridges depend on lower ones.

---

## §2. Hard global constraints

These apply to every bridge. They are not optional.

1. **Files in `carson_dashboard/static/` are LOCKED.** Do not modify
   `index.html`, `dashboard.css`, `dashboard.js`, `cost.js`,
   `replay.js`, `autonomy.js`, `audit.js`, `chats.js`, `pm.js`,
   `autonomous.js`, `ops.js`. The UI is the source of truth.
2. **Existing `/api/*` response shapes are LOCKED.** Add new endpoints,
   never refactor old ones.
3. **Database schemas are append-only.** New `ALTER TABLE ADD COLUMN`
   is fine. Renames or drops are forbidden.
4. **One PR per bridge.** No bundling, no "while I'm here" cleanups.
5. **Heuristic backends ship first.** Haiku 4.5 / CDAOSDK is a
   follow-up PR after the bridge is merged.
6. **If a bridge needs more than 3 files touched outside
   `carson_dashboard/`, stop.** Open an issue describing the unexpected
   coupling. Do not improvise the fix.

---

## §3. Bridge 1 — CHAT (≈ 60 min)

### Goal
The chat input on `#/autonomous` and `#/chats` produces real LangGraph
runs. Agents reply in-channel via SSE events.

### Files to touch
- `carson_dashboard/routes.py` — add 1 endpoint
- `carson_dashboard/webhooks.py` — add `chat_dispatch()` helper
- One agent file in `agents/` — add the chat-message hook
- `langgraph-system/router.py` (or equivalent) — emit classification

### Exact change in `routes.py`

Add after the existing `/api/hitl/request` block:

```python
@router.post("/api/chat/message")
async def api_chat_message(payload: dict = Body(...)) -> JSONResponse:
    text = payload.get("text", "").strip()
    if not text:
        raise HTTPException(400, "text required")
    name = payload.get("name", "you")
    session_id = payload.get("session_id")  # optional — multi_chat will fill

    # Echo immediately
    bus.publish({
        "type": "chat.user_message",
        "session_id": session_id,
        "name": name,
        "text": text,
        "ts": time.time(),
    })

    # Dispatch to the real router (sync for now; SSE handles async replies)
    try:
        result = webhooks.chat_dispatch(text, name=name, session_id=session_id)
    except Exception as e:
        bus.publish({"type": "chat.system",
                     "session_id": session_id,
                     "text": f"router error: {e}",
                     "ts": time.time()})
        raise HTTPException(500, str(e))
    return JSONResponse({"ok": True, **result})
```

### Exact change in `webhooks.py`

Add at the bottom of the file:

```python
def chat_dispatch(text: str, name: str = "you",
                  session_id: str | None = None) -> dict[str, Any]:
    """Bridge the chat input into the existing langgraph router.

    Publishes chat.routing immediately, then defers to the agent run
    (which publishes chat.agent_message + chat.progress + chat.hitl_request
    on its own — see agents/<your_agent>.py).
    """
    cls = classify({
        "summary": text,
        "description": "",
        "labels": [],
        "repo": "",
    })
    bus.publish({
        "type": "chat.routing",
        "session_id": session_id,
        "track": cls.track,
        "agent": cls.agent,
        "confidence": cls.confidence,
        "signals": cls.signals,
    })
    # Drop the actual run on a queue; the agent's existing run loop
    # picks it up and emits chat.agent_message / chat.progress.
    from . import agent_dispatcher  # adjust to your project layout
    agent_dispatcher.enqueue(track=cls.track, agent=cls.agent,
                              text=text, session_id=session_id)
    return {"track": cls.track, "agent": cls.agent}
```

If `agent_dispatcher` doesn't exist, **stop** and ask.

### Exact change in agent files (per agent)

In each agent's main loop (e.g. `agents/aquiles.py`), wrap each phase
transition with a publish:

```python
from carson_dashboard.stream import bus

def run_phase(self, phase_name: str, idx: int, total: int):
    bus.publish({
        "type": "chat.progress",
        "session_id": self._session_id,
        "agent": self.name,
        "job_id": self.job_id,
        "phase": phase_name,
        "idx": idx,
        "total": total,
        "text": self._summary_for(phase_name),
        "ts": time.time(),
    })
    # ... existing phase logic
```

When the agent first picks up a chat-driven job, also publish a
greeting message:

```python
bus.publish({
    "type": "chat.agent_message",
    "session_id": self._session_id,
    "agent": self.name,
    "text": "On it. I'll work in 9 phases — clone → analyze → ...",
    "ts": time.time(),
})
```

### Verification (must all pass)

```bash
# A. Round-trip
curl -X POST http://127.0.0.1:8765/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"text":"refactor jira webhook","name":"martin"}'
# Expected: {"ok":true,"track":"coder","agent":"aquiles"}

# B. SSE emits the events (in another terminal)
curl -N http://127.0.0.1:8765/sse | head -10
# Expected: chat.user_message → chat.routing → chat.agent_message
```

In the browser at `#/autonomous`, type into the chat input. The same
3 events should land in the chat thread with the right avatars.

### Rollback if anything fails

```bash
git checkout HEAD~1 -- carson_dashboard/routes.py
git checkout HEAD~1 -- carson_dashboard/webhooks.py
# revert the agent file edits
```

Then file an issue with the exact error message. Do not patch.

---

## §4. Bridge 2 — REPLAY (≈ 15 min, often a no-op)

### Goal
Confirm `/api/replay/<run_id>/timeline` works on real runs (not just
the simulator's seeded data).

### Files to touch
None, in the common case. If verification fails, edit
`carson_dashboard/instrumentation.py`.

### Verification

```bash
# 1. Find a real run id
curl http://127.0.0.1:8765/api/runs?limit=5

# 2. Pull its timeline
curl http://127.0.0.1:8765/api/replay/<that_run_id>/timeline | jq .swimlanes
# Expected: array of {agent, segments[]} with at least 3 entries
```

In the browser at `#/replay`, the run shows up in the right rail.
Click it. Confirm:

- [ ] Swimlanes draw (≥ 3 lanes)
- [ ] Frame stream has non-empty `text` per line
- [ ] Tool inspector shows args (not "no args")

If any fail, the cause is in `instrumentation.record_step` — the
existing langgraph callback isn't capturing reasoning text. Fix
there. Otherwise, no code change.

### Rollback
N/A (no-op in common case).

---

## §5. Bridge 3 — COST (≈ 90 min)

### Goal
Replace `metrics.cost_summary` and `metrics.leaderboard` fixtures with
real aggregations.

### Files to touch
- `carson_dashboard/autonomous.py` — schema upgrade
- `carson_dashboard/webhooks.py` — write the new column
- `carson_dashboard/metrics.py` — replace fixtures

### Schema upgrade

In `autonomous.py`, add to `_AUTON_SCHEMA`:

```sql
ALTER TABLE autonomous_jobs ADD COLUMN agent TEXT;
```

Wrap in a try/except so the migration is idempotent:

```python
def _migrate_v2() -> None:
    with cursor() as c:
        try:
            c.execute("ALTER TABLE autonomous_jobs ADD COLUMN agent TEXT")
        except sqlite3.OperationalError:
            pass  # already exists
```

Call `_migrate_v2()` from `init_autonomous_db()`.

### Webhook write

In `webhooks.receive_jira`, when calling `ops_db.upsert_ticket(...)`
also update the autonomous_job:

```python
# After the upsert_ticket call:
with cursor() as c:
    c.execute(
        "UPDATE autonomous_jobs SET agent = ? WHERE job_id = ?",
        (cls.agent, job_id),
    )
```

### Replace metrics

In `metrics.py`, replace the leaderboard body:

```python
def leaderboard(limit: int = 10, window_days: float = 30.0) -> list[dict]:
    cutoff = time.time() - window_days * 86400
    with _connect() as c:
        rows = c.execute(
            """SELECT agent, COUNT(*) AS n
               FROM autonomous_jobs
               WHERE started_at >= ? AND agent IS NOT NULL
               GROUP BY agent ORDER BY n DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
    return [{"agent": r["agent"], "prs": r["n"]} for r in rows]
```

In `cost_summary`, drop the `prs_shipped < 50` fallback once telemetry
is ramped (i.e. you can rely on real data). Keep the formula
otherwise.

### Verification

```bash
curl http://127.0.0.1:8765/api/cost/leaderboard
# Should return real agents, not the fixed list of [aquiles, sdlc, ...]
```

In the browser at `#/cost`, the leaderboard reflects real activity.

### Rollback
The new column is harmless if left empty. The metrics revert to the
fixture by reverting `metrics.py`.

---

## §6. Bridge 4 — AUDIT (≈ 90 min)

### Goal
Every meaningful agent action writes a row to `audit_log`.

### Files to touch
- `carson_dashboard/webhooks.py` — add audit calls
- `carson_dashboard/routes.py` — add audit calls in HITL endpoint

### Hook points (must add all 6)

```python
# In webhooks.receive_jenkins, when action == "build_ok" or "build_fail":
audit.insert_audit({
    "actor": "jenkins",
    "event_type": "build",
    "resource": detail,
    "metadata": {"team": team, "raw": raw},
})

# In webhooks.receive_spinnaker, on "rolled_back":
audit.insert_audit({
    "actor": "spinnaker",
    "event_type": "rollback",
    "resource": detail,
    "approved_by": "auto · slo breach",
    "metadata": {"team": team},
})

# In webhooks.receive_github, on "pr_merged":
audit.insert_audit({
    "actor": pr_author,
    "event_type": "approval",
    "resource": detail,
    "approved_by": payload.get("merged_by", {}).get("login"),
})

# In routes.api_autonomous_job_action, on "approve" / "reject":
audit.insert_audit({
    "actor": job["agent"] or "unknown",
    "event_type": "hitl_approve" if action == "approve" else "hitl_reject",
    "resource": f"{job_id} · {job['summary'][:60]}",
    "approved_by": payload.get("actor"),
})

# In athena agents on sync done:
audit.insert_audit({
    "actor": self.name,
    "event_type": "index_sync",
    "resource": f"athena.{self.name}.{self.collection} · {chunks} chunks",
})

# In any data access (where credentials are scoped):
audit.insert_audit({
    "actor": agent_name,
    "event_type": "data_access",
    "resource": f"{scope} · {classification}",
    "approved_by": f"policy {policy_id}",
})
```

### Verification

```bash
# Trigger one of each
curl -X POST http://127.0.0.1:8765/api/ops/jenkins/webhook \
  -H "Content-Type: application/json" \
  -d '{"name":"test-svc","build":{"number":1,"status":"success","phase":"completed"}}'

curl http://127.0.0.1:8765/api/audit/log?limit=5
# The most recent row must be of type "build" with resource "test-svc · #1"
```

In the browser at `#/audit`, click each filter pill — counts must
update without page refresh.

### Rollback
Audit writes are append-only and harmless. Revert the calls in webhooks
to roll back.

---

## §7. Bridge 5 — MULTI_CHAT (≈ 60 min)

### Goal
The `#/chats` view lets multiple conversations run concurrently. Each
session has its own thread + focus + router bias.

### Files to touch
- `carson_dashboard/routes.py` — extend `/api/chats/{id}/messages` POST
- `carson_dashboard/chats.py` — already done; just call from above
- All `chat.*` SSE publishes — add `session_id` field

### Change `routes.api_chats_send`

```python
@router.post("/api/chats/{session_id}/messages")
async def api_chats_send(session_id: str, payload: dict = Body(...)) -> JSONResponse:
    text = payload.get("text", "").strip()
    name = payload.get("name", "you")
    session = chats.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")

    # Persist + echo
    msg_id = chats.append_message(session_id, {
        "type": "user", "name": name, "text": text,
    })
    bus.publish({
        "type": "chat.user_message",
        "session_id": session_id,
        "id": msg_id, "name": name, "text": text,
        "ts": time.time(),
    })

    # Dispatch with session focus as a router hint
    webhooks.chat_dispatch(
        text, name=name, session_id=session_id,
        focus_hint=session["agent_focus"],
    )
    return JSONResponse({"ok": True, "id": msg_id})
```

### Update `chat_dispatch` (in webhooks.py)

Add the `focus_hint` arg and forward to the dispatcher:

```python
def chat_dispatch(text: str, name: str = "you",
                  session_id: str | None = None,
                  focus_hint: str | None = None) -> dict[str, Any]:
    # ... existing code ...
    agent_dispatcher.enqueue(
        track=cls.track, agent=cls.agent,
        text=text, session_id=session_id,
        focus_hint=focus_hint,
    )
    # ...
```

### Persist agent replies into the session

When an agent publishes `chat.agent_message`, also persist via:

```python
chats.append_message(session_id, {
    "type": "agent",
    "agent": agent_name,
    "text": reply_text,
})
```

This is best done in a small helper that wraps both the bus.publish
and the chats.append_message — call it from each agent.

### Verification

Open two browser windows, both on `#/chats`, in different sessions.
Type in one. Confirm:

- [ ] The other window's session shows `unread: 1` badge
- [ ] Switching to that session clears the badge
- [ ] Pinning a session moves it to the top
- [ ] Closing the chat doesn't lose history (refresh, history persists)

### Rollback
Revert `routes.api_chats_send` to its previous signature. Sessions
remain — they just don't bias the router.

---

## §8. Bridge 6 — PM (≈ 120 min)

### Goal
Approving a PM draft (epic / Jira / Confluence page) creates the real
artifact via the existing JPMC MCP servers.

### Files to touch
- `carson_dashboard/pm.py` — add commit functions
- `carson_dashboard/routes.py` — add 3 commit endpoints
- One MCP-bridge file (location depends on your project; ask first)

### Add commit functions in `pm.py`

```python
def commit_epic(draft: dict, project_id: str) -> dict:
    """Calls the real Jira API via the existing MCP server, then
    persists in pm_epics + audit_log + chat_messages."""
    from . import jira_mcp_client  # adjust to your project
    issue = jira_mcp_client.create_issue(
        project=project_id,
        type="Epic",
        summary=draft["title"],
        description=draft["summary"],
        owner=draft.get("owner"),
    )
    epic = create_epic(
        project_id=project_id,
        title=draft["title"],
        summary=draft["summary"],
        owner=draft.get("owner"),
        target_date=draft.get("target_date"),
        jira_key=issue["key"],
    )
    # Audit
    from . import audit
    audit.insert_audit({
        "actor": "pm-agent",
        "event_type": "config_change",
        "resource": f"epic created · {issue['key']} · {draft['title']}",
        "approved_by": draft.get("approved_by"),
        "metadata": {"draft": draft, "issue": issue},
    })
    return {**epic, "jira_url": issue["url"]}


def commit_jira(draft: dict, parent_epic: str | None = None) -> dict:
    # similar shape to commit_epic
    ...


def commit_confluence(draft: dict, space: str) -> dict:
    # similar shape to commit_epic, but via confluence_mcp_client
    ...
```

### Add endpoints in `routes.py`

```python
@router.post("/api/pm/commit/epic")
async def api_pm_commit_epic(payload: dict = Body(...)) -> JSONResponse:
    return JSONResponse(pm.commit_epic(
        draft=payload["draft"],
        project_id=payload["project_id"],
    ))

# ... same for jira, confluence
```

### Verification

In the browser at `#/pm`, type "draft an epic for HNSW migration" in
the PM chat. Confirm:

- [ ] A draft proposal arrives with child tickets
- [ ] Click "approve & create"
- [ ] Network tab shows `POST /api/pm/commit/epic` returning 200
- [ ] A real Jira ticket exists at the returned URL
- [ ] The new epic appears in the left rail without page refresh
- [ ] An audit row of type `config_change` exists

### Rollback
The MCP bridge is the riskiest piece. Wrap each commit_* call in a
try/except that publishes a `chat.system` error and re-raises. Roll
back by reverting the 3 endpoints + 3 commit_* functions.

---

## §9. Demo-day runbook

### 30 min before

```bash
cd C:\repos\high-touch-agent-prompts
git status                    # clean
git pull                      # latest
python -m carson_dashboard    # boot
```

Open Chrome at `http://127.0.0.1:8765/dashboard`.

If you want clean screenshots without the dev chrome:
```
http://127.0.0.1:8765/dashboard?screenshot=1
```

To trigger the 30-second tour during the demo:
```
http://127.0.0.1:8765/dashboard?tour=1
```

### Demo sequence (8-10 min)

1. **Open on `#/cost`** — let the counters animate in. "Carson
   shipped 2,847 PRs autonomously this quarter — that's $1.4M of
   eng-hours saved at $100/h."
2. **Cmd+2** → `#/autonomous` — "Here's how it works. Each agent
   runs in 9 phases. The orange diamonds are where I had to step in."
3. **Cmd+3** → `#/chats` — click "Athena ops" — "And I can talk to
   them. Each conversation has a focus that biases which agent
   responds."
4. **Cmd+4** → `#/pm` — "When I ask the PM agent to draft an epic, it
   proposes a structured Jira ticket. I review, approve, and it's
   created."
5. **Cmd+7** → `#/replay` — pick a job — hit play — "And I can
   replay any past run frame by frame. Tool calls, decisions,
   approvals."
6. **Cmd+9** → `#/audit` — "Every action is logged. Filter by type,
   export to PDF for compliance."

### If something breaks live

- Press the `×` on the keyboard hint pill if it's distracting.
- If a tab errors, hit Cmd+1 to go back to live and continue from
  there. The graph + log are robust.
- If the server dies, `python -m carson_dashboard` boots in < 3s.

---

## §10. Failure protocol

If at any point during a bridge wireup something doesn't match the
expected output:

1. **Stop**. Do not attempt a quick fix.
2. **Capture the failure**: error message, expected vs actual,
   request/response payloads.
3. **Open a GitHub issue** in the working repo. Title:
   `[carson-bridge-N] <one-line summary of what failed>`
4. **Revert the WIP branch**:
   ```bash
   git checkout main
   git branch -D feat/carson-bridge-N
   ```
5. **Report back to Martin** with the issue link.

Do not improvise. Do not "patch around" the symptom. Do not refactor
adjacent code "since I'm already here." Carson is a multi-million-line
production system at JPMorgan; the cost of an undocumented broken
deploy is much higher than the cost of waiting one cycle to ship a
bridge cleanly.

---

## §11. Reference — file map

```
high-touch-agent-prompts/
├── CARSON_INSTRUCTION.md           ← this file (master)
├── CARSON_FULL_WIREUP.md           ← architectural reference
├── CARSON_COPILOT_PROMPT.md        ← paste-ready prompts
├── CHAT_WIREUP.md                  ← legacy (covered by §3)
├── CARSON_AUDIT_FIXES.md           ← prior audit work
├── CARSON_DASHBOARD.md             ← dashboard architecture
└── carson_dashboard/
    ├── __main__.py                 ← entry point, init order
    ├── routes.py                   ← all FastAPI routes
    ├── webhooks.py                 ← Jira/Jenkins/Spinnaker/GitHub receivers
    ├── classifier.py               ← heuristic + Haiku 4.5 slot
    ├── db.py                       ← runs/steps/tool_calls schema
    ├── ops_db.py                   ← jira_tickets/ops_events/notification_rules
    ├── autonomous.py               ← autonomous_jobs/phases + knowledge_agents
    ├── audit.py                    ← audit_log
    ├── chats.py                    ← chat_sessions/chat_messages
    ├── pm.py                       ← pm_projects/epics/deliverables/confluence_pages
    ├── metrics.py                  ← cost + autonomy aggregations
    ├── replay.py                   ← timeline reconstruction
    ├── simulator.py                ← seeded fixtures + live loops
    ├── instrumentation.py          ← langgraph callback bridge (CHAT bridge §3)
    ├── stream.py                   ← SSE event bus
    └── static/                     ← LOCKED — UI source of truth
        ├── index.html
        ├── dashboard.{js,css}
        ├── autonomous.js
        ├── chats.js
        ├── pm.js
        ├── ops.js
        ├── cost.js
        ├── replay.js
        ├── autonomy.js
        └── audit.js
```

---

## §12. Sign-off checklist (before merging any bridge)

- [ ] PR title matches the template `feat(carson): bridge N — <name>`
- [ ] PR description includes the verification checklist (§3-§8) with
      every item ticked
- [ ] No file in `carson_dashboard/static/` is in the diff
- [ ] No existing `/api/*` response shape changed
- [ ] At most 3 files touched outside `carson_dashboard/`
- [ ] At least 1 screenshot of the verified behavior attached
- [ ] Reverting the PR is documented in the description

If all 7 boxes tick, ship it.
