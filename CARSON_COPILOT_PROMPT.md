# Carson Copilot — paste-ready prompt

Open this file in VS Code on the VDI, copy the block below, paste it
into Copilot Chat. Spec it references is `CHAT_WIREUP.md` at the same
repo root (already pushed in commit 6f24aa6).

---

```
@carson-fixer apply CHAT-BEHAVIOR-WIREUP

Read CHAT_WIREUP.md at the repo root before doing anything. The spec
defines the SSE event contract the chat UI listens on. The UI is
fixed and is the source of truth — do not touch carson_dashboard/static/.

Reply with a 5-line plan first. I will confirm before you apply.

Apply only after I confirm, in 4 steps. Stop and report after each.

  Step 1. Add POST /api/chat/message in carson_dashboard/routes.py:
            - publish chat.user_message immediately on the SSE bus (echo)
            - call the existing langgraph router with the user text
            - publish chat.routing with {track, agent, confidence, signals[]}

  Step 2. In each langgraph agent (agents/ or langgraph-system/),
          wrap the run loop so it publishes chat.agent_message on
          greet/ack and chat.progress on each phase transition.
          Re-use the existing webhooks.request_hitl() call sites —
          they already publish hitl.requested; alias that to
          chat.hitl_request via the bus or duplicate the publish.

  Step 3. Add the two missing button actions to
          /api/autonomous/jobs/{id}/{action}: 'refresh' (kicks an
          athena agent sync) and 'dismiss' (no-op ack, just publishes
          chat.agent_message confirming).

  Step 4. Run the verification checklist (A round-trip, B self-init,
          C HITL via chat, D no regressions on live/autonomous/ops/
          history) from CHAT_WIREUP.md. Take a screenshot of each
          and attach to the PR.

Hard constraints — read these twice:
  - Do NOT modify ANY file in carson_dashboard/static/
    (autonomous.js, dashboard.js, dashboard.css, index.html, ops.js
    are LOCKED — even if you think you can improve them)
  - Do NOT change the response shape of any /api/autonomous/* endpoint
  - Do NOT add endpoints other than /api/chat/message
  - One PR titled "feat(chat): wire chat panel to real LangGraph",
    targeting feature/CREDITTECH-241864-agentic-ai-mcp-servers
  - If any agent wireup needs more than 3 files touched, stop and
    open an issue — do not improvise
  - Heuristic classifier ships first. CARSON_CLASSIFIER_BACKEND=haiku
    is a follow-up PR

If at any verification step (A, B, C, D) the result doesn't match the
expected behavior, STOP and report which check failed and why. Do not
patch the symptom — re-plan from Step 1.
```

---

## What to expect from Copilot

After you paste, Copilot replies with a **5-line plan**. Sanity-check
it against this template:

1. `Add POST /api/chat/message endpoint with bus.publish for user_message + routing`
2. `Wrap N agents to emit chat.agent_message + chat.progress events`
3. `Add 'refresh' and 'dismiss' actions to existing /api/autonomous/jobs/{id}/{action} endpoint`
4. `Run verification (A: round-trip, B: self-init, C: HITL, D: no regressions)`
5. `Open one PR titled feat(chat): wire chat panel to real LangGraph`

If Copilot's plan deviates significantly (e.g. "I'll refactor the
router" or "I'll create new files under static/"), **say no** and
ask it to stay on spec.

If the plan looks good, reply: **`confirmed, apply step 1`**

Then verify after each step before moving on:
- After step 1: hit `POST /api/chat/message` with curl, watch SSE
  for `chat.user_message` + `chat.routing`
- After step 2: trigger any agent run, watch SSE for
  `chat.agent_message` and `chat.progress`
- After step 3: click an athena agent's `refresh now` button, see
  it actually sync
- After step 4: confirm Copilot ran A/B/C/D and screenshots attached

## If Copilot breaks something or gets stuck

Tell Copilot:
> stop. revert to last commit. open an issue describing what failed.

Then ping back here with what happened — I write the wireup myself
on the personal branch and you pull.
