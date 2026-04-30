# Carson chat — wire-up contract

The autonomous-view chat panel is **visually complete** and the
**data layer** (jobs, agents, ops events) is wired. What is **NOT**
wired yet is the *behavioural* layer — i.e. the chat input does not
produce a real LangGraph run, and the autonomous agents do not
self-publish into the channel.

This document is the contract Copilot must satisfy. The UI is the
source of truth — do not change it. Adapt the **real** Carson
(`langgraph-system/`, `agents/`) to emit and consume the events below.

---

## SSE event contract

The chat panel listens on `/sse` for these event types. The frontend
is already coded against this exact shape (see
`carson_dashboard/static/autonomous.js` — search for `addEventListener`).

### Events the server EMITS (chat consumes)

| event type | payload (JSON) | when to emit |
|---|---|---|
| `chat.user_message` | `{id, name, text, ts}` | immediately after `/api/chat/message` is hit (echo) |
| `chat.routing` | `{track, agent, confidence, signals[]}` | after the router (haiku 4.5 or heuristic) classifies the user message |
| `chat.agent_message` | `{agent, text, ts}` | when an agent posts a free-form reply (greeting, ack, status) |
| `chat.progress` | `{agent, job_id, phase, idx, total, text, ts}` | on every phase transition of an autonomous job |
| `chat.hitl_request` | `{agent, job_id, text, actions[], ts}` | when an agent calls `webhooks.request_hitl()` |
| `chat.system` | `{text, ts}` | system-level events (channel opened, reconnect, etc.) |

`actions[]` items shape: `{label, kind, action}` where `kind` is
`"primary" | "ghost" | "danger"` and `action` is one of:
`approve | approve_prod | reject | hold | resume | cancel | refresh | dismiss | view`.

### Endpoints the chat CALLS

| method + path | body | behaviour |
|---|---|---|
| `POST /api/chat/message` | `{text, name?}` | publish `chat.user_message` ★ then run the langgraph router ★ publish `chat.routing` with result |
| `POST /api/autonomous/jobs/{id}/{action}` | `{actor?}` | already wired — do NOT change |

The chat panel never polls. SSE is the only delivery channel.

---

## Self-initiated agent messages

Athena knowledge agents (`bob`, `hydra`, `csb`, `pixie`, `studio`,
`sdlc`, `aquiles`) and the coder agents (`aquiles`, `sdlc`) must be
able to post into the chat **without a user prompt**. Triggers:

- Athena agent's index is stale > N hours → `chat.agent_message` with
  a "want me to refresh?" body and a `refresh` / `dismiss` action pair
- Coder agent finishes a deploy → `chat.agent_message` with a status
  recap, no actions
- A downstream agent notices a schema drift caused by another job's
  PR → `chat.agent_message` warning the operator, with a
  `schedule for after merge` / `sync now anyway` action pair
- HITL needed → `chat.hitl_request` (already covered above)

The shape stays the same. The trigger lives inside each agent's
existing run loop — no central scheduler.

---

## Quick replies

The compose footer renders chips that prefill the textarea:

- `@aquiles status` — should resolve to a normal user message
  classified as `coder.aquiles` with `intent=status`
- `@bob refresh now` — direct action, equivalent to clicking the
  refresh button on a stale-index ask
- `@sdlc plan deploy` — direct action, equivalent to a coder.sdlc
  plan-only run
- `show failing tests` — natural-language query, classified normally
- `summarise the last 24h` — natural-language query

The UI emits these as plain `POST /api/chat/message` calls — the
server side does NOT need a special parser. The router decides.

---

## Constraints (Copilot, read this twice)

1. **Do NOT modify** any of: `static/autonomous.js`, `static/dashboard.css`,
   `static/index.html`, `static/dashboard.js`, `static/ops.js`. The
   UI is fixed; behaviour adapts to it, not the other way around.
2. **Do NOT add** new endpoints other than `POST /api/chat/message`.
   Re-use existing ones.
3. **Do NOT change** the shape of any existing `/api/autonomous/*`
   response. The dashboard parses these directly.
4. **Each event is one publish.** Do not batch progress events.
5. **Wire only the missing actions** (`refresh`, `dismiss`).
   `approve` / `approve_prod` / `reject` / `hold` / `resume` /
   `cancel` are already wired through `/api/autonomous/jobs/{id}/{action}`.
6. **If a langgraph agent wireup requires touching more than 3 files**,
   stop and report. The chat behaviour is supposed to be a thin glue
   layer over the existing run loop, not a rewrite.
7. **Heuristic classifier first**, Haiku 4.5 second. Ship with
   `CARSON_CLASSIFIER_BACKEND=heuristic` until prod-cleared.

---

## Verification (Copilot must do these before opening the PR)

### A. Chat round-trip
1. Type a message in the chat input
2. Verify (in browser DevTools → Network → /sse) that the following
   events arrive in order: `chat.user_message`, `chat.routing`,
   `chat.agent_message`
3. Verify the agent reply appears in the chat thread with the right
   avatar color and name

### B. Self-initiated message
1. Force a stale-index condition on `bob`
   (e.g. set `last_sync_at` to 25 hours ago)
2. Verify a `chat.agent_message` with action buttons appears
   without any user input
3. Click `refresh now` — verify the bob agent actually runs a sync

### C. HITL via chat
1. Trigger a coder job that pauses at `review`
   (use the existing simulator if needed)
2. Verify `chat.hitl_request` appears in the chat as an amber-bordered
   card
3. Click `merge now` — verify the job state transitions to `running`
   and the chat shows an `approved · resuming` ack

### D. No regressions
1. Open `/dashboard#/live` — agent graph still draws 7+ Carson nodes
2. Open `/dashboard#/autonomous` — the 4 job cards + 7 athena cards
   still render with the same look
3. Open `/dashboard#/ops` — the 3 lanes + Jira intake still work

---

## Carson Copilot prompt (paste verbatim)

```
@carson-fixer apply CHAT-BEHAVIOR-WIREUP

Spec is in CHAT_WIREUP.md on branch claude/carson-audit-2026-04-27.
Read it end-to-end before starting.

Apply in 4 steps. Stop and report if any verification fails.

  Step 1. Add POST /api/chat/message in carson_dashboard/routes.py:
            - publish chat.user_message immediately (echo)
            - call the existing langgraph router with the user text
            - publish chat.routing with the classifier output

  Step 2. Inside each agent in agents/ (or the equivalent in
          langgraph-system), wrap the run loop so it publishes
          chat.agent_message on greet/ack and chat.progress on each
          phase transition. Re-use the existing webhooks.request_hitl
          for HITL — it already maps to chat.hitl_request via the bus.

  Step 3. Add the two missing actions ('refresh' for athena agents,
          'dismiss' as a no-op ack) in routes.py. The existing
          /api/autonomous/jobs/{id}/{action} endpoint takes them.

  Step 4. Run the verification checklist (A, B, C, D from
          CHAT_WIREUP.md). Take screenshots of A, B, C results and
          attach to the PR.

Constraints — these are hard:
  - Do NOT modify any file in carson_dashboard/static/
  - Do NOT change any /api/autonomous/* response shape
  - Do NOT add endpoints other than /api/chat/message
  - If any langgraph wireup needs > 3 files touched, stop and report
  - Heuristic classifier ships first — leave Haiku for a follow-up PR
  - One PR titled "feat(chat): wire chat panel to real LangGraph"

Reply with a 5-line plan before applying. I will confirm.
```
