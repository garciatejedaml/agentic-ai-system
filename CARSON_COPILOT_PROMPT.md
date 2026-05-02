# Carson Copilot · paste-ready prompts

> **Quick index**
> - **Audit prompt** — paste this when you want Copilot to run the
>   self-audit autonomously (read-only, produces findings docs).
>   Section "Self-audit · paste verbatim" below.
> - **Single bridge wireup** — to wire one of the 6 behaviour bridges.
> - **Full sequence wireup** — to wire all 6 bridges in order with
>   approval between each.
> - **Recovery / rollback** — if a bridge breaks something.

---

## Self-audit · paste verbatim

Use this **first**. Run the audit before any fix work. The audit
produces `audit_outputs/*.md` in the repo. **No fixes are applied
during the audit phase.**

```
@carson-fixer apply CARSON-SELF-AUDIT

Master spec: CARSON_AUDIT_PLAYBOOK.md at the repo root.
Read end-to-end before doing anything. Note the §-numbered phases —
you will execute them in order, 0 through 12.

Output: a folder `audit_outputs/` at the repo root with one MD per
phase plus 00_executive_summary.md and 99_fix_manifest.md.

Templates: `audit_templates/` has fillable stubs. Copy them in:

    cp -r audit_templates audit_outputs

Then fill each in order, executing the phase's procedure.

Reply with:
  1. SHA + branch you're auditing (from §0 pre-flight)
  2. The 12-line plan: one line per phase saying what you'll inspect
I will confirm before you proceed.

Apply only after I confirm. After each phase, commit:
  git add audit_outputs/
  git commit -m "audit: phase N · <area> · <findings_count> findings"

When all phases are done, push to a NEW branch (do NOT push to main):
  git checkout -b audit/repo-<YYYY-MM-DD>
  git push origin audit/repo-<YYYY-MM-DD>

Then file a single chat message to Martin:
  > Self-audit complete. Branch audit/repo-<YYYY-MM-DD>. Findings:
  > X P0, Y P1, Z P2, W P3. See audit_outputs/00_executive_summary.md
  > and audit_outputs/99_fix_manifest.md.

Hard global constraints (§14 of playbook):
  - READ-ONLY phase. No fixes applied. Any urge to "just fix this"
    must be suppressed and recorded in the finding card instead.
  - Do not paste actual secret values into findings — redact with
    <redacted-NN-chars> placeholders.
  - If a phase's procedure errors out, record the error in the
    phase's MD with a "Phase incomplete" banner and continue with
    the next phase.
  - One commit per phase (so reverts are surgical).

Failure protocol:
  - If your audit finds something so urgent it should be fixed
    immediately rather than logged, STOP, file an urgent issue
    titled "[carson-audit-urgent] <one-line>", and continue. Do
    not apply the fix yourself during the audit.
```

---


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
