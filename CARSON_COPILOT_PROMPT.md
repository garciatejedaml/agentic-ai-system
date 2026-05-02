# Carson Copilot — paste-ready prompt for the full wireup

Open this file in VS Code on the VDI, copy the block below, paste it
into Copilot Chat. Spec it references is `CARSON_FULL_WIREUP.md` at
the repo root (synced in the same commit as this file).

The dashboard now has 10 views — most are visually + data complete,
six need behavioural bridges to real Carson. This prompt sequences
them in priority order.

---

## Single bridge — paste verbatim

To wire **just one bridge** (recommended for safety), pick from the
six and paste this:

```
@carson-fixer apply CARSON-BRIDGE-{N}

Spec: CARSON_FULL_WIREUP.md → "Bridge {N}" section.
Read it end-to-end before doing anything.

Reply with a 5-line plan first. I will confirm before you apply.

Apply only after I confirm. Stop and report after each change.
Run the verification checklist for that bridge before opening the PR.

Hard constraints:
  - Do NOT modify any file in carson_dashboard/static/
  - Do NOT change the response shape of any existing /api/* endpoint
  - Do NOT add new tabs (we have 10, that's the ceiling)
  - One PR per bridge
  - If you need > 3 files touched outside carson_dashboard/, stop
    and open an issue
```

Replace `{N}` with one of: `CHAT`, `REPLAY`, `COST`, `AUDIT`,
`MULTI_CHAT`, `PM`.

---

## Full sequence — paste once

To wire **all six bridges** in sequence (one at a time, with my
approval between), paste this longer prompt:

```
@carson-fixer apply CARSON-FULL-WIREUP

Spec: CARSON_FULL_WIREUP.md at repo root.
Read it end-to-end.

This is a SEQUENCE of 6 PRs. Apply them in this order:
  1. CHAT      (already documented; no-op if already done)
  2. REPLAY    (verify only — no code change unless verification fails)
  3. COST      (schema change + aggregation queries)
  4. AUDIT     (write hooks at every state transition)
  5. MULTI_CHAT (federate the chat path per session_id)
  6. PM        (Jira/Confluence commit endpoints)

For EACH bridge, do:
  Step A. Reply with a 5-line plan for THIS bridge only.
  Step B. Wait for my "confirmed" reply.
  Step C. Apply.
  Step D. Run the verification checklist (in CARSON_FULL_WIREUP.md).
  Step E. Open ONE PR for this bridge titled
          "feat(carson): bridge {N} — <short description>"
          targeting feature/CREDITTECH-241864-agentic-ai-mcp-servers.
  Step F. Wait for me to merge before starting the next bridge.

Hard constraints (apply to ALL bridges):
  - Do NOT modify any file in carson_dashboard/static/
  - Do NOT change the response shape of any existing /api/* endpoint
  - Do NOT add new tabs
  - Heuristic classifier ships first; Haiku is a follow-up
  - If any bridge needs > 3 files touched outside carson_dashboard/,
    stop and open an issue. Don't improvise.

Now begin Step A for Bridge 1 (CHAT). What's your 5-line plan?
```

Carson Copilot will reply with the plan for the first bridge. Review
it, type `confirmed` if it looks right, and the loop continues.

---

## Recovery if a bridge breaks something

Tell Copilot:

> stop. revert this bridge. file the failure in an issue with the
> verification check that failed and what you saw. don't try to patch.

Then pull the working state back from `claude/carson-audit-2026-04-27`
on `garciatejedaml/agentic-ai-system` — that branch is your safety
net. Specifically the static/ folder and the routes.py from the latest
green commit.

---

## What to expect — 5-line plan templates

For each bridge, the plan should look like:

**CHAT** (already shipped):
1. Add POST /api/chat/message
2. Wrap N agents to emit chat.agent_message + chat.progress
3. Add 'refresh' and 'dismiss' actions
4. Run verification (A round-trip, B self-init, C HITL, D no regressions)
5. Open one PR titled feat(chat): wire chat panel to real LangGraph

**REPLAY**:
1. Hit /api/replay/<real_run_id>/timeline against existing data
2. If empty or generic, augment instrumentation.record_step calls
3. Verify swimlanes + frame stream + tool calls render
4. No code change if verification passes (most likely outcome)
5. Open one PR (or skip) titled feat(replay): verify against real runs

**COST**:
1. ALTER TABLE autonomous_jobs ADD COLUMN agent
2. Update webhooks.receive_jira to write agent=cls.agent
3. Replace fixture leaderboard with real GROUP BY query
4. Replace 6 hardcoded summary fields with real aggregations
5. Open one PR titled feat(cost): real aggregations from carson telemetry

**AUDIT**:
1. Add audit.insert_audit() calls at the 6 hook points listed in spec
2. Hook into existing webhooks (PR merge, rollback, deploy, sync)
3. Hook into HITL approve/reject in /api/autonomous/jobs/{id}/{action}
4. Verify each hook produces the expected event_type
5. Open one PR titled feat(audit): write hooks for compliance log

**MULTI_CHAT**:
1. Add session_id to all chat.* SSE events
2. Update /api/chats/{session_id}/messages to use existing chat behavior
3. Use session.agent_focus to bias router (per spec table)
4. Verify isolation between two sessions
5. Open one PR titled feat(chats): federate chat behavior per session

**PM**:
1. Add POST /api/pm/commit/{epic|jira|confluence} endpoints
2. Wire to existing Jira/Confluence MCP server
3. Write audit_log on commit; publish chat.agent_message ack
4. Verify draft → approve → real Jira ticket flow
5. Open one PR titled feat(pm): commit drafts to Jira/Confluence

If any of these plans deviate significantly from the templates above,
**say no** and ask Copilot to stay on spec.
