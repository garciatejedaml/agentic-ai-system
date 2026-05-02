# Carson Copilot · paste-ready prompts

Open this file in VS Code on the VDI, copy the relevant block,
paste into Copilot Chat. The single source of truth Copilot will
follow is `CARSON_INSTRUCTION.md` at the repo root.

---

## Single bridge — paste this verbatim

Replace `{N}` with `1` (CHAT), `2` (REPLAY), `3` (COST), `4` (AUDIT),
`5` (MULTI_CHAT), or `6` (PM).

```
@carson-fixer apply CARSON-BRIDGE-{N}

Master spec: CARSON_INSTRUCTION.md at the repo root.
Read end-to-end before doing anything. The §-numbered section that
matches your bridge has the exact code blocks, file list, verification
checklist, and rollback procedure.

Process:
  1. Run §0 pre-flight check. If anything fails, STOP and report.
  2. Reply with the 5-line plan from §11.X (the bridge-specific
     template). I will confirm.
  3. Apply only after I confirm.
  4. After applying, run the verification checklist in §X. ALL boxes
     must tick.
  5. Open ONE PR titled "feat(carson): bridge {N} — <short name>"
     targeting feature/CREDITTECH-241864-agentic-ai-mcp-servers.
     The PR description copies the verification checklist with each
     item marked [x].

Hard global constraints (§2):
  - Files in carson_dashboard/static/ are LOCKED
  - Existing /api/* response shapes are LOCKED
  - DB schemas are append-only
  - One PR per bridge — no bundling
  - If > 3 files touched outside carson_dashboard/, STOP and report
  - Heuristic classifier ships first; Haiku is a follow-up

Failure protocol (§10):
  - If verification fails at any step → STOP, capture error, file
    issue, revert WIP branch, report back. Do NOT improvise.
```

---

## Full sequence — one prompt, six PRs

Use this only after Bridge 1 (CHAT) has merged successfully. It
applies bridges 2 through 6 in order, with your `confirmed` reply
gating each step.

```
@carson-fixer apply CARSON-FULL-SEQUENCE

Master spec: CARSON_INSTRUCTION.md (read it before starting).

This is a SEQUENCE of 5 PRs (bridges 2-6). For each, do:
  Step A. Run §0 pre-flight. If anything fails, STOP.
  Step B. Reply with the 5-line plan for THIS bridge only.
  Step C. Wait for "confirmed" before applying.
  Step D. Apply in order, stopping after each file change.
  Step E. Run the verification checklist for the bridge.
  Step F. Open ONE PR titled "feat(carson): bridge {N} — <name>".
  Step G. Wait for me to merge before starting the next bridge.

Order:
  Bridge 2 — REPLAY     (verify only — no code change in common case)
  Bridge 3 — COST       (schema + queries)
  Bridge 4 — AUDIT      (write hooks at every state transition)
  Bridge 5 — MULTI_CHAT (federate chat path per session_id)
  Bridge 6 — PM         (commit drafts to Jira/Confluence)

Apply ALL global constraints from §2. Apply the failure protocol
from §10 at every step.

Begin with Step A for Bridge 2.
```

---

## What a good plan looks like

Per §3-§8 of CARSON_INSTRUCTION.md, here are the templates Copilot's
plan should match. If the plan deviates significantly, **say no** and
ask Copilot to stay on spec.

### Bridge 1 — CHAT
1. Add POST /api/chat/message in routes.py with bus.publish for user_message + routing
2. Add chat_dispatch() helper in webhooks.py
3. Wrap N agent run loops to emit chat.agent_message + chat.progress
4. Run verification A/B from §3
5. Open one PR titled feat(carson): bridge 1 — chat to LangGraph

### Bridge 2 — REPLAY
1. Run verification (§4): pull a real run timeline + check swimlanes / frame_stream / tool calls
2. If verification passes: no code change
3. If frame_stream is generic: edit instrumentation.record_step to include richer reasoning
4. Re-run verification
5. Open one PR (or skip if no-op) titled feat(carson): bridge 2 — replay verification

### Bridge 3 — COST
1. ALTER TABLE autonomous_jobs ADD COLUMN agent (idempotent migration)
2. Update webhooks.receive_jira to write agent=cls.agent on the job
3. Replace metrics.leaderboard fixture with the GROUP BY query from §5
4. Drop the `prs_shipped < 50` fallback in metrics.cost_summary
5. Open one PR titled feat(carson): bridge 3 — real cost aggregations

### Bridge 4 — AUDIT
1. Add audit.insert_audit() at the 6 hook points listed in §6
2. Hook into webhooks.receive_jenkins / receive_spinnaker / receive_github
3. Hook into routes.api_autonomous_job_action (HITL approve/reject)
4. Hook into athena agent sync completion + any data_access call site
5. Open one PR titled feat(carson): bridge 4 — audit log writes

### Bridge 5 — MULTI_CHAT
1. Update routes.api_chats_send to dispatch via webhooks.chat_dispatch with focus_hint
2. Update chat_dispatch to accept and forward focus_hint to the dispatcher
3. Persist agent replies into chat_messages via a small helper
4. Add session_id field to all chat.* SSE publishes
5. Open one PR titled feat(carson): bridge 5 — federate chat per session

### Bridge 6 — PM
1. Add pm.commit_epic / commit_jira / commit_confluence functions calling existing MCP servers
2. Add 3 endpoints in routes.py: POST /api/pm/commit/{epic|jira|confluence}
3. Each commit writes audit_log + publishes chat.agent_message ack
4. Run verification: draft → approve → real Jira ticket created
5. Open one PR titled feat(carson): bridge 6 — commit drafts to Jira/Confluence

---

## Recovery if something breaks

If a bridge merges and the dashboard breaks, in DevShell:

```powershell
cd C:\repos\high-touch-agent-prompts
git revert <merge-commit-sha>      # creates a revert commit
git push origin feature/CREDITTECH-241864-agentic-ai-mcp-servers
```

Then re-sync `carson_dashboard/static/` from the canonical branch:

```powershell
cd C:\repos\carson-ops-temp
git fetch
git checkout claude/carson-audit-2026-04-27 -- carson_dashboard/static
robocopy carson_dashboard\static C:\repos\high-touch-agent-prompts\carson_dashboard\static /E /NFL /NDL
```

The static layer is the source of truth — restoring it always works.

---

## Demo-day quick reference

The dashboard supports three URL params for the demo:

| URL                                          | What it does                          |
|----------------------------------------------|----------------------------------------|
| `/dashboard`                                 | normal mode                            |
| `/dashboard?screenshot=1`                    | hides connection pill + notifications |
| `/dashboard?tour=1`                          | replays the 30-second onboarding tour  |

Keyboard shortcuts (no modifier needed, just the digit):

| key | tab        |
|-----|------------|
| `1` | live       |
| `2` | autonomous |
| `3` | chats      |
| `4` | pm         |
| `5` | ops        |
| `6` | cost       |
| `7` | replay     |
| `8` | autonomy   |
| `9` | audit      |
| `0` | history    |

`Cmd+/` (or `Ctrl+/`) — focus the active chat input.
