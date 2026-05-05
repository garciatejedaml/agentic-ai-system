# Carson · refactor prompt library

Paste-ready prompts for the refactors that follow each audit. These
prompts apply changes — they are **not** read-only. Every refactor
prompt enforces the change-card protocol from `AGENT_BEHAVIOR_GUARDRAILS.md`
§4: propose, get approval, apply, verify.

Pair each refactor prompt with the corresponding audit findings file
(generated via the prompts in `CARSON_AUDIT_PROMPTS.md`).

The order recommended for pre-demo cleanup:

1. **REFACTOR-RENAME** (legacy names → canonical) — fastest, highest
   visible impact, safe.
2. **REFACTOR-DE-EMOJI** — strip emojis everywhere.
3. **REFACTOR-CARSON-CONSOLIDATE** — single Carson, sub-packages
   keep their `carson_` prefix.
4. **REFACTOR-EXTRACT-CONFIG** — hardcoded values → config.
5. **REFACTOR-LOAD-BASE-SYSTEM** — agents load the constitution
   instead of inlining it.
6. **REFACTOR-LLM-ROUTER** — replace heuristic router with LLM.
7. **REFACTOR-CRITIC-LOOP** — multi-dim critic + directive feedback.
8. **REFACTOR-AUTONOMOUS-VARIANTS** — add `supports_autonomous` +
   per-track phases for git and athena.
9. **REFACTOR-DEDUP** — extract shared modules.
10. **REFACTOR-LANGGRAPH-ROUTING** — every full-mode call goes
    through the orchestrator.
11. **REFACTOR-PERFORMANCE** — case-by-case from the perf audit.
12. **REFACTOR-ASK-BEFORE-CHANGE** — wrap side-effect call sites
    with the HITL gate.

---

## 1. REFACTOR-RENAME

```
@carson-fixer apply REFACTOR-RENAME

Spec:
  - AGENT_BEHAVIOR_GUARDRAILS.md §13 (canonical agent names).
  - audit_outputs/naming_findings.md (the NM-* findings).

Mapping (legacy → canonical):
  Brandson      → bitbucket agent
  Jenkins       → jenkins agent
  Spinnaker     → spinnaker agent
  Inspector     → terraform agent
  Confluence    → confluence agent
  Jira          → jira agent
  Aquiles       → code agent
  SDLC          → release agent
  Athena-Dev    → athena code agent
  Bob           → borrowing knowledge agent
  Hydra         → decision knowledge agent
  CSB           → syndicate knowledge agent
  Pixie         → pricing knowledge agent
  Studio        → ml store knowledge agent

Display rules:
  - Code (class names, file names): BitbucketAgent,
    bitbucket_agent.py, BorrowingKnowledgeAgent,
    borrowing_knowledge_agent.py
  - Prompts: lowercase, hyphen-free, exact form from the table
  - UI labels: capitalize first word ("Bitbucket agent")
  - Logs / traces: lowercase canonical form

Reply with a 5-line plan and a per-file rename table BEFORE
applying. The table must list:
  - file path
  - old identifiers found
  - new identifiers
  - whether it's a class rename, file rename, string replacement
    in prompts, or string replacement in UI

Apply in 3 commits, in this order, each one a separate PR-able
unit:

  Commit 1 — class + file renames (Python). Includes:
    - Rename the agent class (e.g., AquilesAgent → CodeAgent)
    - Rename the file (aquiles_agent.py → code_agent.py)
    - Update imports in callers
    - Update `name` field in registration
    - Update the test files

  Commit 2 — prompt-text renames. Includes:
    - System prompt strings that mention legacy names
    - Tool docstrings that mention legacy names
    - The router's agent catalog descriptions

  Commit 3 — UI / dashboard renames. Includes:
    - carson_dashboard/static/* references in seeded data
    - audit_log entries that contain legacy names
      (only update going-forward defaults; don't rewrite history)

Constraints:
  - Do NOT rename folders or files inside carson_dashboard/static/
    (the static layer is locked per CARSON_INSTRUCTION.md)
  - Do NOT touch git history
  - Stop and report if a rename would create a name collision
    with an existing identifier
  - Verify after each commit that:
      python -m pytest tests/ -x
    passes (or, if tests don't exist, that imports still resolve:
      python -c "import agents; import langgraph_system")

If a finding refers to a legacy name in a third-party file
(README, vendor code, examples), KEEP the legacy name and add
a note to the finding card that it's an external reference.

One PR per commit. Title format:
  "refactor(naming): rename legacy agents — commit N of 3"
```

---

## 2. REFACTOR-DE-EMOJI

```
@carson-fixer apply REFACTOR-DE-EMOJI

Spec: AGENT_BEHAVIOR_GUARDRAILS.md Invariant 7.

Find all emojis in the codebase and replace them with words or
remove. Use the audit at audit_outputs/naming_findings.md for the
target list.

Replacement guide:
  ✓ ✅ → "ok" / "done" / "passed"
  ✗ ❌ → "fail" / "failed"
  ⚠️ → "warning" / "warn"
  📌 → "pinned"
  🔥 → (remove entirely)
  ⚡ → (remove entirely)
  🎯 → (remove entirely)
  → (the actual character) → "→" stays — it's punctuation, not
    emoji
  ⏵ ⏸ ⏪ ⏩ ⏮ ⏭ → keep ONLY in carson_dashboard/static/index.html
    media controls (the dashboard's player UI) — those are
    functional UI symbols, not communication emojis

Apply per-file. Reply with the affected file count and a sample
of 10 replacements before applying. Apply in one commit per
domain:

  Commit 1 — agent prompts (agents/*.py)
  Commit 2 — MCP servers (mcp-servers/**/*.py)
  Commit 3 — orchestrator (langgraph-system/*.py)
  Commit 4 — docs (*.md at root, docs/*)
  Commit 5 — dashboard non-static (carson_dashboard/*.py only —
    static/* is locked)

Constraints:
  - Static dashboard files are locked
  - Don't touch test fixtures that explicitly test emoji parsing
  - Don't touch CHANGELOGs / historical docs
  - Stop if an emoji appears inside a string that's an input to
    a test (means we'd change behavior, not just style)

Verify after each commit:
  - The agent's reply tone changed (run one example)
  - Tests still pass
  - The dashboard still renders

One PR per commit. Title:
  "refactor(de-emoji): strip emojis from <domain> · commit N of 5"
```

---

## 3. REFACTOR-CARSON-CONSOLIDATE

```
@carson-fixer apply REFACTOR-CARSON-CONSOLIDATE

Spec: AGENT_BEHAVIOR_GUARDRAILS.md §14.

Goal: there is one Carson. Multiple Carson-something names exist
in the codebase. Per §14, the resolution table:

  Carson           → keep — the brand
  Carson-admin     → "carson admin console" (a UI surface)
  Carson-fixer     → rename to "fix agent" (in the agent pool)
  carson_dashboard → keep (sub-package)
  carson_data      → keep (sub-package)
  carson_kb        → keep (sub-package)

Reply with a 5-line plan and a per-file change table BEFORE
applying. Distinguish:
  - User-facing strings (dashboard UI, agent self-introduction,
    chat output, email/Slack messages): apply renames
  - Sub-package names in source tree: KEEP
  - Code / file system identifiers (class names, file paths) for
    sub-packages: KEEP
  - Code / file system identifiers for the renamed agents
    (Carson-fixer → fix agent): apply rename per
    REFACTOR-RENAME rules

Key locations to inspect:
  - .github/agents/carson-fixer.agent.md → rename file + change
    the agent name inside to "fix agent"
  - Any "Carson Admin" UI text in carson_dashboard/static/* —
    SKIP (static is locked); flag for a follow-up
  - Any "Carson-admin" in code → rename to "carson admin
    console" if it refers to the UI, or keep if it refers to a
    code module

Constraints:
  - Static dashboard files are locked
  - The Copilot custom agent file (.github/agents/) IS in scope —
    the rename of `carson-fixer` to `fix agent` happens here
  - Update CARSON_COPILOT_PROMPT.md to use the new agent name
  - Update the Copilot invocation header in every prompt block
    (the @carson-fixer reference becomes @fix-agent)

One PR titled:
  "refactor(branding): single Carson; consolidate Carson-fixer → fix agent"
```

---

## 4. REFACTOR-EXTRACT-CONFIG

```
@carson-fixer apply REFACTOR-EXTRACT-CONFIG

Spec: audit_outputs/hardcoding_findings.md (HC-* findings) +
AGENT_BEHAVIOR_GUARDRAILS.md Invariant 5.

Goal: every hardcoded URL / path / model id / magic number moves
to a config layer. The config layer has 3 tiers:

  1. **carson/config/defaults.py** — hardcoded but documented as
     "default; override in env or per-team config". Used when
     env / per-team config doesn't specify.
  2. **environment variables** — for env-specific values
     (proxy, region, endpoints).
  3. **carson_data/project_profiles/<team>.json** — for per-team
     values (Bitbucket project key, Jira project, slack channel).

Reply with a categorized plan: which finding goes to which tier,
and the estimated diff per file.

Apply per cluster:

  Cluster A — model IDs.
    Create carson/config/models.py with a single MODEL_CONFIG dict.
    Replace every hardcoded model id with MODEL_CONFIG[<name>].
    Update tests.

  Cluster B — URLs and proxies.
    Create carson/config/endpoints.py reading from env vars with
    documented defaults.
    Replace every hardcoded URL.

  Cluster C — magic numbers.
    Per file, add a CONFIG dataclass at the top with the values
    pulled from the body. Replace literal use sites.

  Cluster D — per-team values.
    Move to carson_data/project_profiles/<team>.json schema.
    Write a small loader in carson/config/profiles.py.

  Cluster E — paths.
    Replace Windows-specific paths with `pathlib.Path` derived
    from the project root or env. Fail loud on missing env if
    no sensible default exists.

Constraints:
  - For each cluster, write ONE PR
  - Do NOT change observable behavior — every default must match
    the value previously hardcoded
  - Stop if a hardcoded value has multiple call sites with
    DIFFERENT values (means there's a bug already; flag for
    separate triage)
  - Don't refactor test fixtures unless they test config loading
    itself

After applying, document the new config in CARSON_INSTRUCTION.md
with one line per env var.

PR title format:
  "refactor(config): extract <cluster> from source · cluster X of E"
```

---

## 5. REFACTOR-LOAD-BASE-SYSTEM

```
@carson-fixer apply REFACTOR-LOAD-BASE-SYSTEM

Spec: AGENT_BEHAVIOR_GUARDRAILS.md §15 + CARSON_PATTERNS.md §2.

Today some agents inline the base system content into their own
prompts. This causes:
  - Drift (one agent's preamble differs from another's)
  - Bloat (token cost in every call)
  - Drift from AGENT_BEHAVIOR_GUARDRAILS.md updates

Goal: every agent loads the canonical guardrails via
load_base_system() and concatenates its agent-specific prompt.

Apply per-agent. Reply with a 5-line plan + a per-agent before/
after diff sample BEFORE applying.

Implementation:

  agents/_base.py  (new):

    from pathlib import Path
    import hashlib

    _BASE_PATH = Path(__file__).parents[1] / "AGENT_BEHAVIOR_GUARDRAILS.md"
    _CACHED: tuple[str, str] | None = None

    def load_base_system() -> str:
        global _CACHED
        if _CACHED is None:
            text = _BASE_PATH.read_text()
            sha = hashlib.sha256(text.encode()).hexdigest()[:12]
            _CACHED = (text, sha)
        return _CACHED[0]

    def base_system_hash() -> str:
        load_base_system()
        return _CACHED[1]

  agents/<each>_agent.py:

    from ._base import load_base_system

    BASE_SYSTEM = load_base_system()
    AGENT_SYSTEM = "..."   # was previously the FULL prompt

    class XAgent(...):
        def __init__(self, ...):
            super().__init__(
                ...,
                system_prompt=BASE_SYSTEM + "\n\n# Agent identity\n" + AGENT_SYSTEM,
            )

Verification:
  - Every agent's effective prompt now starts with the constitution
  - The constitution hash (from base_system_hash()) is logged at
    agent-construction time
  - The langgraph orchestrator (per the existing pattern) verifies
    every agent's system prompt starts with the expected hash

Constraints:
  - Apply ONE agent per commit; one PR per commit
  - Don't break any agent that already has the correct pattern
  - Stop if an agent's existing AGENT_SYSTEM contradicts the
    constitution (means the agent has rules that override
    invariants — that's a separate decision)

PR title format:
  "refactor(prompts): <agent> loads base system from constitution"
```

---

## 6. REFACTOR-LLM-ROUTER

```
@carson-fixer apply REFACTOR-LLM-ROUTER

Spec: CARSON_PATTERNS.md §8 + audit_outputs/routing_findings.md.

Goal: replace the heuristic keyword router with an LLM-based one.

Apply in 3 commits:

  Commit 1 — introduce the LLM router as opt-in.
    - Implement langgraph-system/router.py per CARSON_PATTERNS.md §8
    - The system prompt loads the agent catalog at construction
      from the registry (NOT a hardcoded list)
    - Default model: Haiku 4.5 (or current fast Anthropic model
      via MODEL_CONFIG)
    - The router exposes a `classify(request)` function returning
      the JSON schema in §8.
    - Wire it into the dispatch path under the env flag
      CARSON_ROUTER_BACKEND=llm. Default still heuristic.
    - Add tests: 10 sample requests with expected agents.

  Commit 2 — migration.
    - Add structured logging on every classification: which
      backend ran, what it returned, what the heuristic would
      have returned. This is the migration data.
    - Run for 7 days minimum (note: this is a deploy step, not a
      code step — STOP after Commit 2 and ask the human to
      schedule the migration window).

  Commit 3 — flip + delete.
    - Default to LLM backend.
    - Heuristic becomes the fallback (only on LLM unavailable).
    - After 30 more days of < 0.1% fallback rate, delete the
      heuristic entirely (separate PR).

Reply with a 5-line plan BEFORE applying Commit 1. The plan must
include:
  - The exact Haiku prompt template you'll use
  - How the agent catalog is rendered into the prompt
  - The fallback semantics
  - The tests you'll add

Constraints:
  - Do NOT remove the heuristic in this refactor (only deprecate)
  - Do NOT change the public shape of the classifier function
    (callers must be unchanged)
  - The LLM router uses MODEL_CONFIG, not a hardcoded model id
  - Stop if the agent catalog (from the registry) is empty or
    incomplete — fix the registry first

PR title:
  "refactor(routing): LLM-based router (commit N of 3)"
```

---

## 7. REFACTOR-CRITIC-LOOP

```
@carson-fixer apply REFACTOR-CRITIC-LOOP

Spec: CARSON_PATTERNS.md §9 + audit_outputs/critic_findings.md.

Goal: replace boolean retry loops with multi-dimensional critic
verdicts that produce actionable directives.

Apply per agent OR per orchestrator path, depending on where the
loop lives.

Implementation steps (reply with a plan BEFORE applying):

  Step 1 — implement langgraph-system/critic.py per §9 of
  CARSON_PATTERNS.md. The critic agent:
    - Takes (task, candidate_output) → verdict JSON
    - Has its own system prompt (CRITIC_SYSTEM constant)
    - Uses MODEL_CONFIG['critic'] (a different model than the
      primary agent)

  Step 2 — wire the critic into one agent loop as the proof of
  concept. Pick the highest-volume agent (likely 'code agent').
  The loop becomes:
    while loop_count < MAX_LOOPS:
        candidate = primary.run(task + previous_directive)
        verdict = critic.run(task=task, candidate=candidate)
        if verdict.verdict == "approve":
            return candidate
        if verdict.verdict == "reject":
            escalate_to_hitl(verdict.rationale)
            return
        previous_directive = verdict.directive
        loop_count += 1
    escalate_to_hitl("loop exceeded MAX_LOOPS")

  Step 3 — set MAX_LOOPS = 3 globally; deprecate the legacy
  MAX_WORKFLOW_STEPS = 100 guard.

  Step 4 — extend to remaining agents one PR at a time.

Constraints:
  - Do NOT change the user-facing API of any agent
  - The critic verdict shape is fixed; do NOT add new fields
    without proposing a §9 update first
  - The critic has access to the same tools as the primary agent
    (read-only) — it can't write or delegate
  - Stop if the primary agent has a tool that produces side
    effects during candidate generation (e.g., commits before
    critic approval) — those need to be moved to AFTER critic
    approval; that's a separate refactor

After applying Step 2, run 50 sample tasks and report:
  - Approve rate
  - Average loops per task
  - HITL escalation rate
  - Token cost per task vs. before

PR title:
  "refactor(critic): multi-dim critic loop for <agent> · step N"
```

---

## 8. REFACTOR-AUTONOMOUS-VARIANTS

```
@carson-fixer apply REFACTOR-AUTONOMOUS-VARIANTS

Spec: CARSON_PATTERNS.md §10.

Goal: extend bitbucket agent and the athena knowledge agents with
autonomous-mode support so they can take Jira tickets end-to-end.

Implementation:

  Step 1 — add `supports_autonomous` and `autonomous_phases` to
  the agent base mixin. Existing agents default to:
    supports_autonomous = False
    autonomous_phases = []

  Step 2 — for the bitbucket agent (formerly Brandson):
    supports_autonomous = True
    autonomous_phases = ["intake", "plan", "branch", "diff", "test",
                         "commit", "pr", "review", "merge"]

  Step 3 — for each athena knowledge agent (borrowing, decision,
  syndicate, pricing, ml-store):
    supports_autonomous = True
    autonomous_phases = ["intake", "scan", "snapshot", "embed",
                         "validate", "swap", "prune", "audit",
                         "archive"]
    HITL gates at: "swap" (the destructive one) and "prune"

  Step 4 — the autonomous orchestrator (langgraph-system/
  autonomous_runner.py or equivalent) reads autonomous_phases
  from the agent — NOT from a hardcoded constant. If the
  orchestrator currently has a hardcoded phase list, that's the
  bug to fix.

  Step 5 — the LLM router includes autonomous-supporting agents
  in its candidate pool when classifying autonomous tickets.

Reply with the per-agent change table BEFORE applying. List which
agents you'll touch and the phase template per agent.

Constraints:
  - Do NOT add autonomous support to agents that don't logically
    have a multi-phase task pattern (e.g., the audit agent —
    that's a one-shot)
  - HITL gates at destructive phases are MANDATORY — if you can't
    figure out which phase is destructive, stop and ask
  - Each agent gets its own PR for the autonomous-mode addition

PR title:
  "feat(autonomous): <agent> · autonomous mode support"
```

---

## 9. REFACTOR-DEDUP

```
@carson-fixer apply REFACTOR-DEDUP

Spec: audit_outputs/duplication_findings.md (DUP-* findings).

Goal: extract duplicated code into shared modules. Apply per
cluster.

For each P0/P1 finding:

  Step 1 — propose the extraction:
    - Where the new shared module lives
    - The function/class signature
    - Each call site's adapter (usually trivial; sometimes needs
      arg-shape change)

  Step 2 — implement the shared module + tests.

  Step 3 — migrate each call site. ONE call site per commit if
  the migration is non-trivial; otherwise ALL call sites in one
  commit.

  Step 4 — delete the now-unreferenced duplicated code.

Reply with the cluster-by-cluster plan BEFORE applying.

Constraints:
  - Don't extract trivial duplicates (< 10 LOC)
  - Don't merge agents that share boilerplate but are
    intentionally distinct (separation of concerns matters more
    than DRY for agent prompts)
  - Verify each call site after migration with the existing tests
  - If tests don't cover a call site you migrated, ADD a test
    before merging the cluster's PR

PR title:
  "refactor(dedup): extract <thing> into shared module"
```

---

## 10. REFACTOR-LANGGRAPH-ROUTING

```
@carson-fixer apply REFACTOR-LANGGRAPH-ROUTING

Spec: AGENT_BEHAVIOR_GUARDRAILS.md Invariant 3 +
audit_outputs/mode_respect_findings.md.

Goal: every full-mode call goes through the langgraph orchestrator.
Direct LLM/MCP calls in agent code are eliminated (or explicitly
documented as exempt).

Apply per file:

  For each direct call site in the audit:

  Step 1 — classify:
    - Is it inside `mode == 'full'` code path? (P0)
    - Is it documented as exempt with a clear reason? (skip)
    - Is it test/fixture code? (skip)

  Step 2 — for each P0:
    - Replace the direct call with a delegation through the
      orchestrator's API (or the agent's tool surface, depending
      on the call type).
    - For LLM calls: route via langgraph_system.dispatch_llm
    - For MCP calls: route via langgraph_system.dispatch_mcp
    - For sub-agent invocations: emit a delegation event and let
      the orchestrator route it

  Step 3 — verify telemetry:
    - Token usage now visible in the dashboard's cost view
    - The audit log captures the call
    - The replay view shows the call as a tool_call event

Reply with the per-file plan BEFORE applying. List each call site
and the proposed rewrite.

Constraints:
  - Don't break agents that depend on a specific behavior of the
    direct call (e.g., custom retry policy) — the orchestrator
    must support that behavior or be extended first
  - One PR per agent or per MCP server
  - Stop if a call site has no orchestrator equivalent — that's a
    pattern gap; flag for adding to CARSON_PATTERNS.md

PR title:
  "refactor(routing): route <agent> calls through orchestrator"
```

---

## 11. REFACTOR-PERFORMANCE

```
@carson-fixer apply REFACTOR-PERFORMANCE

Spec: audit_outputs/perf_findings.md (O-PERF-* findings).

Apply per finding (these are surgical, not bulk).

For each finding:

  Step 1 — confirm the issue with a measurement (concrete numbers,
  not "feels slow"):
    - Latency before
    - Query count before
    - Token count before (if applicable)

  Step 2 — propose the fix per the finding's category:
    - N+1 → batch query
    - Sync I/O in async → switch to async client
    - Unbounded loop → add bounded condition
    - No timeout → add timeout per the policy in
      carson/config/endpoints.py
    - Repeated LLM calls → enable caching (Anthropic prompt cache
      or local memo)
    - File I/O in loop → hoist out

  Step 3 — measure after:
    - Latency
    - Query/call count
    - Token count

  Step 4 — if the fix didn't materially improve the metric,
  revert and document why.

Reply with one plan per finding BEFORE applying.

Constraints:
  - One PR per finding (these are isolated changes, easy to revert)
  - Always measure before AND after; "looks faster" is not
    sufficient
  - Don't bundle perf fixes with feature work
  - Stop if the fix requires touching agent prompts (perf is
    behavioral; prompt changes are a different review)

PR title:
  "perf: <one-line summary> (finding O-PERF-XX)"
```

---

## 12. REFACTOR-ASK-BEFORE-CHANGE

```
@carson-fixer apply REFACTOR-ASK-BEFORE-CHANGE

Spec: AGENT_BEHAVIOR_GUARDRAILS.md Invariant 1 +
audit_outputs/confirmation_findings.md (CONF-* findings).

Goal: every side-effect call site has a HITL gate, OR is
explicitly inside an autonomous-mode block.

For each P0/P1 finding:

  Step 1 — identify the call site and its callers up the stack.

  Step 2 — pick the gate location:
    - At the agent boundary (preferred): the agent's run loop
      pauses before invoking the side-effect tool, emits a
      hitl_request event, and waits for approval
    - Inside the tool (fallback): the tool itself calls
      request_hitl and waits, but only when not in autonomous
      mode

  Step 3 — implement the gate using the existing pattern in
  carson_dashboard/webhooks.py::request_hitl.

  Step 4 — write a test that verifies:
    - In full mode: the side effect doesn't execute until
      approval
    - In autonomous mode within scope: the side effect executes
      with no human prompt
    - In autonomous mode OUT of scope: agent stops and reports

Reply with the per-call-site plan BEFORE applying.

Constraints:
  - Don't gate informational writes (audit log, telemetry) —
    those are by-design auto-executed
  - Don't gate rollback paths — those are by-design auto-executed
  - Don't gate test/fixture side effects
  - One PR per agent (multiple call sites within the same agent
    can share a PR if they're related)

PR title:
  "fix(safety): HITL gate at <call site> · finding CONF-XX"
```

---

## How to chain refactors safely

For pre-demo cleanup, run audit prompts first (in the order from
CARSON_AUDIT_PROMPTS.md), then run refactor prompts in the
recommended order at the top of this file.

After EACH refactor PR merges, re-run the corresponding audit to
verify the findings count went down. If it didn't, the refactor
was incomplete — open an issue, don't bundle a fix into the next
refactor.

The full pre-demo cleanup is roughly 12 refactor PRs. If that
sounds like a lot — it is. The choice is between paying the cost
once now or paying it forever as the codebase scales to more
teams.

If demo time is tight, the minimum-viable cleanup before showing
externally is:

1. REFACTOR-RENAME (visible, fast, low risk)
2. REFACTOR-DE-EMOJI (visible, fast, low risk)
3. REFACTOR-EXTRACT-CONFIG cluster B (URLs only, the rest is
   internal)
4. REFACTOR-CARSON-CONSOLIDATE (visible)
5. The other refactors land post-demo as a sprint.
