# CARSON EXECUTION PLAN — Safe Sequence for Audits + Refactors

> Master playbook. Each wave is a stop gate. Do NOT skip smoke tests. If a wave breaks the system, rollback to the previous tag — do not patch forward.

---

## WHY IT BROKE LAST TIME (diagnosis)
Likely root causes when refactors are run back-to-back without gates:
1. Multiple refactors touched the same files in sequence without intermediate verification.
2. Behavioral refactors (LLM router, critic loop) ran before structural ones (config extraction, consolidation), so they were rebuilding on shifting ground.
3. No git checkpoint per wave — when something broke at step N, rollback meant losing N-1 good steps.
4. No smoke test definition — "system works" was vibe-checked, not measured.
5. The Carson consolidation refactor changed routing assumptions while old code still referenced `Carson-admin` / `Carson-fixer`.

This plan removes all five of those failure modes.

---

## THREE RULES (non-negotiable)
1. **One wave at a time.** Never queue two waves in a single Carson session.
2. **Tag before, smoke test after.** Every wave starts with `git tag` and ends with the smoke test passing.
3. **Roll back, don't patch forward.** If smoke test fails, `git reset --hard <previous-tag>` and re-plan. Do not try to fix the broken state by running another prompt.

---

## PRE-FLIGHT (do once before starting)
1. Confirm working tree is clean: `git status` shows nothing.
2. Confirm you are on a fresh branch off main: `git checkout -b carson-cleanup-$(date +%Y%m%d)`.
3. Tag the baseline: `git tag baseline-pre-cleanup`.
4. Take a SQLite + Chroma snapshot:
   - `cp -r ./carson_dashboard/*.db ./_snapshot_$(date +%Y%m%d)/`
   - `cp -r <chroma_path> ./_snapshot_chroma_$(date +%Y%m%d)/`
5. Confirm Carson can boot and a basic flow works (this is your "good" reference state).
6. Open `CARSON_AUDIT_PROMPTS.md`, `CARSON_REFACTOR_PROMPTS.md`, `CARSON_ATHENA_AUDIT_PROMPT.md` in tabs — you'll need them.

If any pre-flight step fails, STOP. Fix the baseline before touching anything else.

---

## SMOKE TEST DEFINITION (run after every wave)
A wave is "passing" only if ALL of these are true:

1. `python -c "import server"` (or your entrypoint) succeeds with no error.
2. The dashboard boots: `uvicorn server:app` (or equivalent) starts without exception.
3. A reactive flow runs: send one user message, get one agent response, observe at least one tool call in the trace. No exceptions.
4. A deterministic flow runs: trigger one autonomous job, see it transition through at least 2 states. No exceptions.
5. The agent rooms view loads in the dashboard. At least one room renders.
6. ChromaDB query works: run a sample retrieval and confirm > 0 hits.
7. `git diff <previous-tag>` is reviewable (changes are scoped to what the wave intended — no surprise files modified).

If ANY of (1)-(7) fails: ROLLBACK. Do not run the next wave.

Document smoke test result in `outputs/cleanup_log.md` per wave with timestamp + pass/fail + notes.

---

## EXECUTION SEQUENCE (9 waves + Athena waves)

The order is chosen so that **each wave operates on a stable foundation built by the previous one**. Cosmetic before structural before behavioral.

### WAVE 0 — AUDITS (READ-ONLY, no risk)
**Goal:** Generate findings. Zero code changes.

**Prompts to run** (in order, can be parallel sessions):
1. `CARSON_AUDIT_PROMPTS.md` → A (Performance)
2. → B (Duplication)
3. → C (Hardcoding)
4. → D (Confirmation)
5. → E (Prompt-override)
6. → F (Mode-respect)
7. → G (Routing)
8. → H (Critic-loop)
9. → I (Naming)
10. → J (Pattern-violations)
11. → K (Kerberos)
12. `CARSON_ATHENA_AUDIT_PROMPT.md` (full)

**Output:** `outputs/audit_findings/` populated with one .md per audit.

**Stop gate:** Read every finding. Produce a personal triage list: which findings are P0 (blocking), which are duplicates of other findings, which are intentionally deferred.

**Tag:** `git tag wave-0-audits-done` (no code changes, but marks the cutoff).

**Smoke test:** N/A (read-only).

---

### WAVE 1 — COSMETIC (low risk, mechanical)
**Goal:** Rename agents to `{capability} agent` form, strip emojis. Mechanical, large file count but no behavior change.

**Prompts:**
- `CARSON_REFACTOR_PROMPTS.md` → 1. RENAME
- → 2. DE-EMOJI

**Tag before:** `git tag wave-1-start`

**After Carson runs both:**
- Diff review: `git diff wave-1-start` should show only string replacements in agent names and emoji removals. No logic changes.
- If you see logic changes (function signatures, control flow), STOP — Carson over-stepped.

**Smoke test:** Full suite. Pay special attention to (3) reactive flow — old hardcoded references to `Carson-admin` will break here if any were missed.

**Tag after:** `git tag wave-1-done` if smoke passes.

---

### WAVE 2 — CONFIG EXTRACTION (low risk, additive)
**Goal:** Pull hardcoded values into config. Behavior preserved.

**Prompts:**
- `CARSON_REFACTOR_PROMPTS.md` → 4. EXTRACT-CONFIG
- → 5. LOAD-BASE-SYSTEM

**Tag before:** `git tag wave-2-start`

**Diff review:** Should show new config files (e.g., `config/carson.yaml`, `config/agents.yaml`) and existing files reading from config instead of hardcoding. Logic should be unchanged.

**Smoke test:** Full suite. Specifically confirm that values in config match what was hardcoded — if Bob job timeout was 300s hardcoded, it should be 300s in config.

**Tag after:** `git tag wave-2-done`

---

### WAVE 3 — CARSON CONSOLIDATION (medium risk)
**Goal:** Single Carson identity. Remove `Carson-admin` / `Carson-fixer` duplicates.

**Prompts:**
- `CARSON_REFACTOR_PROMPTS.md` → 3. CARSON-CONSOLIDATE

**Tag before:** `git tag wave-3-start`

**Pre-check:** Wave 2 must be done. Without config extraction, consolidation will leak hardcoded references.

**Diff review:** Old Carson variants should be deleted. References in routing should point to single Carson. System prompt should be loaded from one source.

**Smoke test:** Full suite. Special attention to routing — confirm the LLM-routed (or keyword-routed for now) decisions still go to the right place after consolidation.

**Tag after:** `git tag wave-3-done`

**If smoke fails:** Most common cause is a stale reference in a registration table or langgraph node. Rollback and re-read the audit on Naming + Pattern-violations.

---

### WAVE 4 — DEDUPLICATION (low risk, additive deletes)
**Goal:** Remove duplicate patterns surfaced by audit B.

**Prompts:**
- `CARSON_REFACTOR_PROMPTS.md` → 9. DEDUP

**Tag before:** `git tag wave-4-start`

**Diff review:** Should show net deletions. If net additions, Carson misunderstood the prompt.

**Smoke test:** Full suite.

**Tag after:** `git tag wave-4-done`

---

### WAVE 5 — ROUTING (HIGH RISK — biggest change)
**Goal:** LangGraph-routed orchestration + LLM-based router replacing keyword heuristics.

**Prompts:**
- `CARSON_REFACTOR_PROMPTS.md` → 10. LANGGRAPH-ROUTING
- → 6. LLM-ROUTER

**Tag before:** `git tag wave-5-start`

**Pre-check:** Waves 1-4 must all be done and stable for at least 24h of light use. The router refactor is the riskiest single change in the entire plan.

**Critical:** Run prompt 10 FIRST (langgraph routing structural), smoke test, THEN run prompt 6 (LLM router behavioral). Do not bundle.

**Sub-tag:** After prompt 10 passes smoke, `git tag wave-5a-done`. Then prompt 6.

**Diff review for prompt 10:** Routing tables → langgraph nodes + edges. Conditional edges visible. MAX_WORKFLOW_STEPS guard in place.

**Diff review for prompt 6:** Keyword regex routers replaced by LLM call (Haiku 4.5 by convention). Agent catalog passed as system prompt. Confidence threshold present.

**Smoke test:** Full suite, run TWICE — once normal, once with an ambiguous user message that previously hit a keyword router. Confirm the LLM router picks a sensible agent.

**Tag after:** `git tag wave-5-done`

**If smoke fails:** This is where rollback hurts most because Wave 5 touches a lot. Do it anyway. Re-plan: most likely the agent catalog passed to the router is incomplete, or the LLM is timing out without a fallback.

---

### WAVE 6 — BEHAVIOR (medium risk)
**Goal:** Multi-dim critic loop + ask-before-change guardrail.

**Prompts:**
- `CARSON_REFACTOR_PROMPTS.md` → 7. CRITIC-LOOP
- → 12. ASK-BEFORE-CHANGE

**Tag before:** `git tag wave-6-start`

**Diff review:** Critic outputs should be structured (correctness, style, completeness, tests, performance, scope_respect) not boolean. ASK-BEFORE-CHANGE should add explicit confirmation prompts at HITL gates per `AGENT_BEHAVIOR_GUARDRAILS.md` Invariant 1.

**Smoke test:** Full suite + a test where you intentionally ask the agent to make a change. Confirm it asks before applying.

**Tag after:** `git tag wave-6-done`

---

### WAVE 7 — AUTONOMOUS TRACKS (medium risk)
**Goal:** Per-track autonomous variants (coder, git, athena, infra) + Kerberos hygiene.

**Prompts:**
- `CARSON_REFACTOR_PROMPTS.md` → 8. AUTONOMOUS-VARIANTS
- → 13. KERBEROS

**Tag before:** `git tag wave-7-start`

**Diff review:** Each autonomous track should be a separate config + entry, not a forked agent class. Kerberos refresh should be centralized, not scattered.

**Smoke test:** Full suite + trigger one autonomous job per track. Each should reach at least the planning phase without error.

**Tag after:** `git tag wave-7-done`

---

### WAVE 8 — POLISH (low risk)
**Goal:** Performance fixes from audit A, agent quality improvements.

**Prompts:**
- `CARSON_REFACTOR_PROMPTS.md` → 11. PERFORMANCE
- → 14. IMPROVE-AGENTS

**Tag before:** `git tag wave-8-start`

**Smoke test:** Full suite + measure: dashboard load time, average agent response time, token usage per turn. Compare against baseline.

**Tag after:** `git tag wave-8-done`

---

### WAVE 9 — SDLC AUTONOMOUS FLOW (NEW — see slot below)
**Goal:** Fix the SDLC autonomous-commit flow you described — review approval → commit → test monitor → retry on failure → ticket comment → final commit.

This refactor does NOT exist yet in `CARSON_REFACTOR_PROMPTS.md`. I will write it as Refactor #15 SDLC-COMMIT-FLOW. **Do not run this wave until the prompt is written and reviewed.**

What it must cover:
- State machine for the post-approval phase: `approved → committing → testing → (passed | failed) → (commenting | retrying)`.
- Retry budget with exponential backoff.
- Test failure parsing (which tests failed, line numbers, root cause classification).
- Auto-fix attempt with critic loop, capped at N retries.
- HITL escalation when retry budget exhausted.
- Final state: ticket comment with summary of what was done + commit pushed + ticket transitioned.

Tag pattern: `wave-9-start`, `wave-9-done`.

---

### ATHENA WAVES (separate sequence, after Wave 8)

Run `CARSON_ATHENA_AUDIT_PROMPT.md` first to generate findings. Then a Wave 10 that fixes Wave 1 of the Athena audit's fix manifest. Treat Athena waves like a parallel track — they do not depend on Wave 9 and can start immediately after Wave 8.

- **WAVE A0** — Athena audit (read-only).
- **WAVE A1** — Athena fix manifest Wave 1 (highest priority gaps).
- **WAVE A2** — History chain harvester (git → JIRA → parents).
- **WAVE A3** — Multi-view embeddings + AST chunking.
- **WAVE A4** — Cross-repo extension.

Each follows the same tag/smoke/tag pattern.

---

## ROLLBACK RECIPE
If a wave's smoke test fails:

1. STOP. Do not run another prompt.
2. Capture the failure: `git diff <wave-tag-start> > outputs/wave_N_failure.diff`. Save logs.
3. `git reset --hard <wave-N-start>`.
4. Restore SQLite/Chroma snapshots if the wave touched data:
   - `cp -r ./_snapshot_<date>/*.db ./carson_dashboard/`
   - `cp -r ./_snapshot_chroma_<date>/* <chroma_path>/`
5. Confirm smoke test passes again (you should be back to wave-(N-1)-done state).
6. Open the failure diff in a fresh Carson session and ask: "Why did this break smoke test step X? Do not modify code, just diagnose."
7. Decide: re-run with a tighter prompt scope, OR defer this wave and continue past it.

**Do NOT run the same prompt twice expecting a different result without changing the input.** Carson is deterministic at temperature 0; if it broke once, it will break again.

---

## STOP CONDITIONS (when to pause and ask, not push through)
Pause and reach out (or take a break and come back fresh) if any of these happen:
- Two consecutive waves fail smoke.
- A single wave's diff is more than 3x the size you expected.
- Carson modifies files outside the wave's stated scope (e.g., DE-EMOJI prompt touches routing logic).
- You see Carson invent new agent names or new file paths that weren't asked for.
- ChromaDB collections change unexpectedly (size jumps or drops).
- Smoke test step (5) — agent rooms view — fails without a related prompt being run.

These are signs of cascade or scope creep, not normal refactor noise.

---

## TIMELINE EXPECTATION
- WAVE 0 (audits): 1 working day (parallelize sessions).
- WAVES 1-4 (cosmetic + structural foundation): 1 working day total.
- WAVE 5 (routing): 1 full day, with buffer for rollback.
- WAVES 6-8 (behavior + autonomous + polish): 1-2 working days.
- WAVE 9 (SDLC): 0.5-1 day after the prompt is written.
- ATHENA WAVES: 2-3 days.

Total realistic for a clean run: **5-7 working days**. Do not compress to 1 day — that is what broke it last time.

---

## EXECUTION LOG TEMPLATE
Maintain `outputs/cleanup_log.md` with one entry per wave:

```
## Wave N — <name>
- Started: 2026-MM-DD HH:MM
- Tag before: wave-N-start
- Prompts run: <ids>
- Diff size: +X / -Y across N files
- Smoke test result: PASS | FAIL
- Tag after: wave-N-done | <not tagged, rolled back>
- Notes: <anything Carson did unexpected>
```

This log is the audit trail you'll want when something subtle breaks 3 days later.

---

## START HERE
Right now, your next concrete step is:

1. Pre-flight (above).
2. Open WAVE 0 list.
3. Run audit A first (Performance) in a fresh Carson session.
4. When A is done, START A NEW SESSION for audit B.
5. Continue through K + Athena audit, ONE PER SESSION.
6. After all audits, do triage before touching Wave 1.

Do not start Wave 1 today if Wave 0 is not fully reviewed and triaged.
