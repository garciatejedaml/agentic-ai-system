# Carson Copilot · paste-ready prompts

> **Behavioral foundation**
> Every prompt below assumes Copilot is bound by the
> behavioral constitution at `AGENT_BEHAVIOR_GUARDRAILS.md`.
> If Copilot deviates from any invariant (asks before changing,
> no assumptions, langgraph-routed, no prompt overrides, no
> hardcoding, surface tradeoffs, stop on ambiguity, no emojis,
> canonical names, single Carson, reuse patterns), say "no" and
> point it back to the relevant section.
>
> Reference docs at the repo root, in priority order:
> - `AGENT_BEHAVIOR_GUARDRAILS.md` — the constitution
> - `CARSON_PATTERNS.md` — canonical patterns (ingestion, agents,
>   MCP tools, registration, LLM router, critic, autonomous variants)
> - `CARSON_AUDIT_PROMPTS.md` — read-only audit prompts (10 prompts)
> - `CARSON_REFACTOR_PROMPTS.md` — refactor prompts that apply changes
> - `CARSON_INSTRUCTION.md` — bridge wireup runbook
> - `CARSON_AUDIT_PLAYBOOK.md` — full repo self-audit playbook



> **Quick index**
> - **Audit prompt** — paste this when you want Copilot to run the
>   self-audit autonomously (read-only, produces findings docs).
>   Section "Self-audit · paste verbatim" below.
> - **Single bridge wireup** — to wire one of the 6 behaviour bridges.
> - **Full sequence wireup** — to wire all 6 bridges in order with
>   approval between each.
> - **Recovery / rollback** — if a bridge breaks something.

---

## Agent rooms wireup · paste verbatim

Use this AFTER the dashboard merge has landed. Wires the new
`#/groups` view to the real Carson runtime so user messages in a
room actually drive a langgraph run and the strands intermediate
events stream back as the trace.

```
@carson-fixer apply AGENT-ROOMS-WIREUP

Goal: connect the new /#/groups view to the real Carson runtime.
The view + endpoints + schema are already shipped in the merge.
This bridge replaces the mocked router fallback in
routes.api_agent_room_send with a real langgraph dispatch, and
adds publishers in each agent that emit strands events into the
room's trace.

Scope: ONLY the agent_rooms wireup. Do NOT touch carson_dashboard/
static files, the audit kit, or any other behavior bridge.

Reply with a 5-line plan and the per-event mapping table BEFORE
applying. I will confirm.

Resolution rules:

  Step 1. In carson_dashboard/routes.py, replace the mocked body of
  api_agent_room_send with a call to webhooks.dispatch_room_message
  (you'll create this helper). The endpoint must STILL append the
  user_message event synchronously and emit agent_room.event over
  SSE — those parts of the existing handler are correct.

  Step 2. In carson_dashboard/webhooks.py, add:
    dispatch_room_message(room_id, text, name)
      - Look up the room via agent_rooms.get_room(room_id)
      - If room.agent in {'router', None} → call the real router
        (heuristic + haiku per CARSON_INSTRUCTION.md §3 Bridge 1)
      - If room.agent is a known agent name → bypass router, dispatch
        directly to that agent's strands run
      - On the langgraph callback hooks, append events to the room
        via agent_rooms.append_event AND publish on the bus

  Step 3. Add per-event mapping in the strands callback handler:
    LangGraph callback           Strands event_type to append
    ───────────────────────────  ───────────────────────────────
    on_chain_start                thinking (with kind='plan')
    on_llm_start                  (no event — internal)
    on_llm_end                    (no event — internal)
    on_tool_start                 tool_call
    on_tool_end                   tool_result
    on_agent_action               delegation (if cross-agent)
    on_agent_finish               agent_message
    webhooks.request_hitl(...)    hitl_request

  Step 4. SSE event shape — every appended event also publishes:
    {
      "type": "agent_room.event",
      "room": <room_id>,
      "event_type": <one of the 9 types>,
      "actor": <agent name>,
      "payload": <event-specific>,
      "ts": <unix>
    }
  The frontend already listens for agent_room.event; do not change
  the shape.

After applying:
  - Verify in browser at /dashboard#/groups :
    1. Click "+ new room"
    2. Pick agent "aquiles" + title "test refactor"
    3. Send a message: "fix the bug in webhook_handler.py"
    4. Within 5s, the room shows: routing → thinking → tool_call →
       tool_result → ... → hitl_request OR agent_message
  - Verify another room (existing aquiles room with J-2417) still
    renders its seed trace correctly (no regression).
  - Take screenshots of (a) new room post-creation, (b) existing
    room with full trace. Attach to the PR.

Constraints:
  - Do NOT modify any file in carson_dashboard/static/
  - Do NOT change the response shape of /api/agent-rooms/* endpoints
  - Do NOT change the SSE event shape (room, event_type, actor, payload, ts)
  - Heuristic classifier ships first — Haiku is a follow-up
  - One PR titled "feat(rooms): wire agent_rooms to real strands runtime"
  - If a strands callback hook isn't available in your version, STOP
    and ask — do not improvise an event mapping
```

---

## Dashboard internal merge · paste verbatim

Use this when Claude's new dashboard is staged inside
`carson_dashboard/newDashboard/` and you want Copilot to merge it
into the main `carson_dashboard/` while preserving your existing
Copilot-only files.

```
@carson-fixer apply DASHBOARD-INTERNAL-MERGE

Context: I have two versions of carson_dashboard inside the same repo:
  - C:\repos\high-touch-agent-prompts\carson_dashboard
    (your current version with signals.py, bridge.py,
    athena_developer_bob_job.py, custom chat input, etc.)
  - C:\repos\high-touch-agent-prompts\carson_dashboard\newDashboard
    (Claude's version with 6 new views, premium chat panel, polish
    animations, keyboard shortcuts, onboarding tour — synced from
    branch claude/carson-audit-2026-04-27 commit 7c2cbcc)

Goal: merge the new dashboard's improvements into my main dashboard,
preserving all my unique work.

Reply with a 5-line plan and a per-file conflict resolution table
BEFORE applying. I will confirm.

Resolution rules — apply strictly:

  Files in newDashboard/ that DON'T exist at carson_dashboard/ root
    → COPY them up. Expected new files:
      - carson_dashboard/cost.js, replay.js, autonomy.js, audit.js,
        chats.js, pm.js (frontend views)
      - carson_dashboard/static/cost.js, replay.js, autonomy.js,
        audit.js, chats.js, pm.js (frontend per-view modules)
      - carson_dashboard/audit.py, chats.py, metrics.py, pm.py,
        replay.py (backend modules)

  Files at carson_dashboard/ root that DON'T exist in newDashboard/
    → KEEP as-is. (signals.py, bridge.py, athena_developer_bob_job.py,
    plus any other Copilot-only files.)

  Files in BOTH that diverge:
    static/index.html, static/dashboard.js, static/dashboard.css,
    static/autonomous.js, static/ops.js
      → Use newDashboard's verbatim (the 10-tab nav, templates,
        CSS sections 1-18, keyboard shortcuts, animations, and
        onboarding tour are interlinked and must be kept whole).
    routes.py → UNION of endpoints. Keep all my routes AND add new
      ones from newDashboard. Expected new endpoints:
      - /api/cost/summary, /api/cost/comparison,
        /api/cost/leaderboard, /api/cost/autonomy-trend
      - /api/autonomy/summary, /api/autonomy/skills
      - /api/replay/recent, /api/replay/{run_id}/timeline
      - /api/audit/log, /api/audit/stats, /api/audit/export
      - /api/chats (GET/POST), /api/chats/{id}, /api/chats/{id}/messages,
        /api/chats/{id}/pin, /api/chats/{id} (DELETE)
      - /api/pm/projects (GET/POST), /api/pm/epics (GET/POST),
        /api/pm/deliverables (GET/POST), /api/pm/confluence,
        /api/pm/draft/epic, /api/pm/draft/jira, /api/pm/draft/confluence
    simulator.py → UNION of seed functions. Expected new seeds:
      - seed_audit_history(), seed_chat_sessions()
    __main__.py → UNION of init calls and seed calls. Expected adds:
      - audit.init_audit_db(), chats.init_chat_db(), pm.init_pm_db()
      - simulator.seed_audit_history(), simulator.seed_chat_sessions()
      - pm.seed_demo()
    Any other .py → UNION of functions. If two functions have the
      same name with different bodies, STOP and ask me.

After applying:
  - Delete the carson_dashboard/newDashboard/ folder (it was a
    staging area; the merge consumes it).
  - Clean __pycache__: rm -rf carson_dashboard/__pycache__
  - Verify the server boots: python -m carson_dashboard
  - Verify all 10 tabs render at http://127.0.0.1:8765/dashboard:
    live · autonomous · chats · pm · ops · cost · replay · autonomy
    · audit · history
  - Take a screenshot showing the 10 tabs and attach to the PR.
  - Open ONE PR titled "merge(dashboard): adopt new views from
    claude branch" targeting feature/CREDITTECH-241864-agentic-ai-mcp-servers.

Constraints:
  - Do NOT modify any file outside carson_dashboard/.
  - Do NOT introduce new pip dependencies (the new modules use
    only stdlib + the existing FastAPI/sse-starlette/uvicorn).
  - Do NOT delete signals.py, bridge.py, athena_developer_bob_job.py,
    or any other file you added. Those are mine.
  - Stop and ask me if any non-trivial code conflict appears.
  - One PR. No bundling with other work.

If your 5-line plan deviates from these rules, I will say "no" and
ask you to re-plan.
```

---

## ChromaDB ingestion · paste verbatim

Use this every time you need to embed/re-embed something into a
ChromaDB collection. Designed to handle the common failure modes
(HNSW corruption, credential expiry mid-run, partial writes) that
happen on the VDI.

```
@carson-fixer apply INGEST-CHROMA

Spec: CARSON_PATTERNS.md §1 (canonical ingestion path).

Goal: ingest a corpus into a ChromaDB collection, with health checks
before / after, credential-refresh handling, and resume-on-failure.

Reply with a 5-line plan and the exact ingestion parameters BEFORE
running. I will confirm.

Required parameters (ask me if any is unclear):
  - source path:        <ABS path to source corpus>
  - collection name:    <athena.bob | athena.hydra | ... per profile>
  - chunker:            AstChunker | MdChunker | TextChunker (default
                        per file extension; ask if mixed)
  - embedder:           BedrockEmbedder · titan-embed-text-v2 (default)
  - reranker:           LlmReranker (default) | none
  - resume_id:          if a previous run failed, the run id to
                        resume from (else 'new')

Steps (in this exact order — do NOT skip any):

  Step 1 — Pre-flight health check (read-only):
    a. Locate the canonical client at carson_kb/ingest.py (per §1).
       Do NOT instantiate a new chromadb.PersistentClient anywhere.
    b. Verify the collection's HNSW index is healthy:
         - Open the collection.
         - Query a known sentinel ('__health_check__') with k=1.
         - If it raises HnswError / dimension mismatch / corrupted
           segment → report, STOP. Do not attempt ingestion until
           the index is repaired.
    c. Verify credentials with a no-op Bedrock call (embed the
       string '__creds_check__'). If it raises auth errors or
       proxy errors, STOP and report — do NOT attempt to re-auth
       silently or fall back to a different provider.
    d. Snapshot the current chunk count + last-modified timestamp.
       This is the rollback target if the run fails.

  Step 2 — Plan the ingestion (read-only):
    a. Walk the source path; produce the file list.
    b. For each file, run the chunker DRY (no embedding) to get
       chunk count.
    c. Estimate: total chunks · total embedding tokens · cost.
    d. Report: "Will ingest N files → M chunks → ~T tokens → ~$X.
                Resume id: <uuid>. Confirm to proceed."
    e. STOP and wait for 'confirmed' before any write.

  Step 3 — Execute (idempotent, batched):
    a. Process in batches of 32 chunks per Bedrock call (default).
    b. After every batch, persist the resume cursor so the next
       run can pick up where this stopped.
    c. On any error during a batch:
         - If transient (timeout, rate limit): retry up to 3 times
           with exponential backoff. Log every retry.
         - If credential expiry / proxy auth: STOP. Do NOT
           silently re-auth. Return the resume id and error so the
           human can re-run with fresh credentials.
         - If HNSW corruption: STOP immediately. Do NOT continue
           writing to a corrupted index — that compounds the
           damage.
    d. After all batches successful: write the run manifest to
       carson_kb/runs/<resume_id>.json with start ts, end ts,
       file list, chunk count, embedder version, model id.

  Step 4 — Post-flight health check:
    a. Re-query the sentinel '__health_check__'. Same shape
       expected.
    b. Verify chunk count delta matches the planned delta from
       Step 2.
    c. Run a sample similarity search with 5 known queries; verify
       recall hasn't regressed (compare top-3 hits with snapshot
       from Step 1d).
    d. If any post-flight check fails, do NOT mark the run
       successful — flag for human review.

Constraints:
  - Use only the canonical ingest function in carson_kb/. Do NOT
    write a new ingestion script.
  - Do NOT change embedder model mid-run.
  - Do NOT silently mix chunkers — one file = one chunker.
  - Do NOT overwrite an existing collection without explicit
    'destroy' parameter set true (which I will pass only when I
    really mean it).
  - Do NOT proceed past Step 1 if any health check fails.
  - Do NOT proceed past Step 2 without my 'confirmed'.
  - On corruption: report, do not 'fix it real quick'. The index
    repair is a separate operation.
  - One Carson telemetry log entry per batch, with batch_id, chunk
    count, latency, token count.

If you encounter a case not covered by this prompt (e.g., the source
contains a binary format we haven't seen), STOP and propose adding
to CARSON_PATTERNS.md §1 before deviating.
```

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
