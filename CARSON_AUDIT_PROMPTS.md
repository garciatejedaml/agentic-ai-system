# Carson · audit prompt library

Paste-ready audit prompts. Each is **read-only** — produces findings,
not fixes. Findings live under `audit_outputs/<area>_findings.md`
and follow the schema in `CARSON_AUDIT_PLAYBOOK.md` §15.

Each prompt is self-contained. Pick the one you need and paste it
into Copilot Chat.

The fixes for any finding go through the corresponding refactor
prompt in `CARSON_REFACTOR_PROMPTS.md`.

---

## A. Performance audit

```
@carson-fixer apply AUDIT-PERFORMANCE

Goal: identify performance issues. Read-only — no fixes during
this audit.

Categories to check (capture one finding card per hit):

1. **N+1 queries** — `for x in collection: db.query(...)` in agent
   tools, dashboard endpoints, MCP server handlers. Look for:
     grep -rn "for.*in.*:" --include="*.py" | grep -v ".venv" \
       | xargs -I {} sh -c 'echo {}' | head -200
   then inspect each loop body for DB or HTTP calls.

2. **Sync I/O in async paths** — `requests.get`, `time.sleep`,
   blocking file reads inside `async def`. Look for:
     grep -rEn "async def" --include="*.py" -A 20 \
       | grep -E "requests\.|time\.sleep|open\(.*['\"]r"

3. **Unbounded loops** — `while True:`, `for _ in range(huge):`,
   `MAX_WORKFLOW_STEPS = 100` style guards. Each unbounded loop is
   a P1 finding unless its termination is provably bounded by the
   data shape.

4. **MCP calls without timeout** — every `httpx.get`, `requests.get`,
   `urllib.urlopen` against an MCP server must have an explicit
   timeout < 30s. Untimed calls are P0.

5. **LLM call repetition** — same prompt to the same model in one
   run. Look in agent run loops for places that re-invoke an LLM
   without caching. Anthropic prompt caching should cover the
   system prompt; if it's not enabled, that's a P1.

6. **File reads inside hot loops** — `open(path).read()` inside
   any iteration. Hoist out.

7. **Logs in hot paths** — `logger.debug` or `print` inside loops
   that run > 100 times per request. Each is a P2.

For each finding, fill the card per CARSON_AUDIT_PLAYBOOK.md §15
with category prefix `O-PERF-` (O for observability/performance).

Output: audit_outputs/perf_findings.md.

Constraints:
  - Read-only — no fixes
  - Quote 1-3 lines of code per finding (no whole functions)
  - For each P0/P1, also include a one-line measurement plan
    (how would we verify the fix worked — latency? query count?)
  - Stop at 50 findings; report "more found, audit incomplete"
    if you exceeded
```

---

## B. Duplication / DRY audit

```
@carson-fixer apply AUDIT-DUPLICATION

Goal: identify code that is duplicated and should be extracted into
a shared module. Read-only.

Approach:
1. Use jscpd, ast-grep, or pylint's similar-lines (whichever is
   already installed; do NOT install new tools — flag if none
   available):
     pylint --disable=all --enable=R0801 \
       --min-similarity-lines=8 -r n agents/ langgraph-system/

2. Manually scan for:
   - Retry loops appearing in > 1 agent (target for §1 of patterns)
   - LLM call setup boilerplate in > 1 agent
   - Logging configuration repeated per file
   - Auth token loading repeated per MCP server
   - Pydantic model definitions that overlap > 70%
   - The 'BASE_SYSTEM' / preamble copy-pasted into agent prompts
     (should load from AGENT_BEHAVIOR_GUARDRAILS.md per §2 of
     CARSON_PATTERNS.md)

3. For each duplication cluster, identify:
   - All files where it appears
   - The proposed shared location
   - The estimated LOC reduction

Severity:
  P0 — duplication that causes bugs (e.g., same retry policy,
       fixed in one place but not the other)
  P1 — > 50 LOC duplicated across > 2 files
  P2 — boilerplate; clean up batch-style
  P3 — small repetitions; tolerable

Output: audit_outputs/duplication_findings.md with category
prefix `DUP-`. Each finding lists ALL clones, not just the first
two. Use the schema from CARSON_AUDIT_PLAYBOOK.md §15 with an
extra "all_clones" field.

Constraints:
  - Read-only
  - Don't propose merges that would break the agent's identity
    (e.g., athena agents share boilerplate but have distinct prompts
    by design — not duplication, separation of concerns)
  - Flag if any cluster includes the AGENT_BEHAVIOR_GUARDRAILS.md
    content — that means an agent isn't loading the constitution
    via the canonical path
```

---

## C. Hardcoding audit

```
@carson-fixer apply AUDIT-HARDCODING

Goal: every URL, path, credential, model id, magic number that's
baked into source instead of config. Read-only.

Categories:

1. **URLs** —
     grep -rEn "https?://[a-zA-Z0-9.-]+" \
       --include="*.py" --include="*.yaml" --include="*.json" \
       --exclude-dir=.venv --exclude-dir=.git . \
       | grep -v "test\|fixture\|example.com\|localhost"

2. **Windows paths** —
     grep -rEn "[A-Z]:[/\\\\]" --include="*.py" --include="*.ps1" \
       --exclude-dir=.venv .

3. **Hardcoded emails / employee IDs** —
     grep -rEn "[a-z0-9._-]+@[a-z0-9.-]+\.[a-z]{2,}|F[0-9]{6}" \
       --include="*.py" --exclude-dir=.venv \
       | grep -v "test\|fixture\|example"

4. **Model IDs** — anything matching:
     grep -rEn "anthropic\.claude|claude-[0-9]|claude-sonnet|claude-haiku|titan-embed|amazon\." \
       --include="*.py" --exclude-dir=.venv .
   These should ALL come from a single MODEL_CONFIG dict.

5. **Magic numbers** — timeouts, retry counts, batch sizes, port
   numbers, max iterations literally in code. Look for:
     grep -rEn "(timeout|retries|max_|batch_size|port)\s*=\s*[0-9]+" \
       --include="*.py" --exclude-dir=.venv .

6. **Region / account ids** — `us-east-1`, `us-west-2`, AWS account
   numbers, etc. Should come from env config.

For each finding:
  - Severity: P0 if it's a credential, P1 if URL/region/path that
    breaks adoption by other teams, P2 if magic number, P3 if it's
    a config that sensibly defaults.
  - Proposed location: the appropriate config file (env var name,
    YAML path, or new dataclass field).
  - **Redact actual secret values** — placeholder
    `<redacted-NN-chars>`.

Output: audit_outputs/hardcoding_findings.md, category prefix
`HC-`.

Constraints:
  - Read-only
  - Do not paste credentials into the file
  - Do not propose moving to .env if the value is multi-tenant
    (must be in a per-team config instead)
  - Don't flag genuinely-fixed values (e.g., HTTP status codes,
    well-known ports like 443) as hardcoding
```

---

## D. Assumption-and-confirmation audit

This audit checks whether agents respect Invariant 1 of the
behavior guardrails: ask before changing.

```
@carson-fixer apply AUDIT-CONFIRMATION

Goal: identify code paths where an agent acts unilaterally on
non-reversible side effects without asking the human.

Categories of side effects to check (one finding per call site):

1. File writes / deletes:
     grep -rn "\.write_text\|\.write_bytes\|os\.remove\|shutil\." \
       --include="*.py" agents/ langgraph-system/

2. Git operations:
     grep -rn "git_commit\|git_push\|git_merge\|git_rebase\|create_pr" \
       --include="*.py" agents/ langgraph-system/

3. External writes — Jira, Confluence, Bitbucket, Spinnaker,
   Jenkins, etc.:
     grep -rn "\.create\|\.update\|\.delete\|\.merge\|\.deploy\|\.transition" \
       --include="*.py" mcp-servers/ agents/

4. Notifications:
     grep -rn "send_email\|post_slack\|notification\|webhook" \
       --include="*.py" agents/

For each call site, determine:
  - Is there a HITL gate before this call? (search for
    `request_hitl`, `approval_pending`, `awaiting_approval` in the
    surrounding code)
  - If not, is the path explicitly inside an `autonomous_mode`
    block?
  - If neither, this is a finding.

Severity:
  P0 — destructive op (delete, force-push, prod deploy) without
       gate
  P1 — write op (commit, create PR, send email) without gate
  P2 — informational write (audit log, telemetry) without gate
       — usually fine, flag as nice-to-have

Output: audit_outputs/confirmation_findings.md, category prefix
`CONF-`. Each finding includes:
  - The call site
  - The chain of callers (who reaches this code path)
  - Whether any caller has a HITL gate
  - Proposed gate location

Constraints:
  - Read-only
  - Don't false-positive on test files (mocks of side effects are
    fine)
  - Don't false-positive on rollback paths (those are by-design
    auto-executed)
```

---

## E. Prompt-override audit

This audit looks for places where an agent's system prompt could
be overridden at runtime — a violation of Invariant 4.

```
@carson-fixer apply AUDIT-PROMPT-OVERRIDE

Goal: find any code path where one agent modifies another agent's
prompt, where a runtime instruction can replace a system prompt,
or where prompt content comes from user-controlled input without
sanitization.

Categories:

1. Prompt mutation in code:
     grep -rn "system_prompt\s*=\|system_prompt\s*+=\|\.system\s*=" \
       --include="*.py" agents/ langgraph-system/

2. Concatenation of user input into system prompt:
     grep -rn "system_prompt.*+.*request\|system_prompt.*+.*user_input" \
       --include="*.py" .

3. Prompt loaded from a writeable location (not source-controlled):
     grep -rn "open.*prompt\|read.*prompt" --include="*.py" .
   Then check whether any `*.md` or `*.txt` it opens is in a
   user-writable folder vs. source control.

4. Agents that `import` other agents' prompt strings and modify
   them.

5. Calls to model providers that pass `system_prompt=request_field`
   where `request_field` is user-controlled.

For each finding:
  - P0: user input directly concatenated into system prompt
  - P1: agent A modifies agent B's prompt
  - P2: prompt loaded from writable location (not source)

Output: audit_outputs/prompt_override_findings.md, prefix `PO-`.

Constraints:
  - Read-only
  - Document the data flow (where does the override-able value
    come from)
  - Distinguish "loads BASE_SYSTEM at construction" (legit) from
    "modifies system_prompt at runtime" (not legit)
```

---

## F. Mode-respect audit

This audit verifies Invariant 3: full-mode tasks route through
the langgraph service.

```
@carson-fixer apply AUDIT-MODE-RESPECT

Goal: find code paths that bypass the langgraph orchestrator when
the active mode is `full`. Read-only.

Categories:

1. Direct LLM provider calls outside langgraph:
     grep -rn "BedrockClient\|AnthropicClient\|OpenAIClient" \
       --include="*.py" agents/ mcp-servers/
   Each hit should be inside the langgraph service module
   (langgraph-system/) or in a clearly-scoped util. Hits in
   agent files are P0 findings.

2. Direct MCP server calls bypassing the registry:
     grep -rn "httpx\.\(get\|post\)\|requests\.\(get\|post\)" \
       --include="*.py" agents/
   Cross-reference with `langgraph_system/registry.py::register_mcp_server`.

3. Direct sub-agent invocation:
     grep -rn "Agent(.*).run(\|agent\.run(\|\.invoke(" \
       --include="*.py" agents/
   Cross-agent invocation should go through the orchestrator's
   delegation, not direct calls.

4. Hardcoded provider config that bypasses the central
   MODEL_CONFIG:
     grep -rn "model_id\s*=\s*[\"']" --include="*.py" .

For each finding, identify:
  - The direct call site
  - The mode the surrounding code runs in (full / autonomous /
    read-only / dry-run)
  - Whether the bypass is documented + justified, or silent

Severity:
  P0 — bypass in code that runs in `full` mode by default
  P1 — bypass in autonomous mode without a documented reason
  P2 — bypass in tooling / scripts (sometimes legitimate)

Output: audit_outputs/mode_respect_findings.md, prefix `MODE-`.

Constraints:
  - Read-only
  - Test files / fixtures are exempt
  - `sys.exit(0)` or similar genuinely-no-LLM paths are exempt
```

---

## G. Routing audit (heuristic vs LLM)

```
@carson-fixer apply AUDIT-ROUTING

Goal: identify routing decisions still made by keyword heuristics
where they should be LLM-classified per CARSON_PATTERNS.md §8.

Categories:

1. Keyword routing dictionaries:
     grep -rn "keyword\|TRACK_\|ROUTE_\|classify_heuristic" \
       --include="*.py" .

2. `if X in text:` chains in router code:
     grep -rEn "if .+ in (text|prompt|summary|description)\.lower" \
       --include="*.py" .

3. Static keyword lists per agent:
     grep -rn "ATHENA_KEYWORDS\|CODER_SIGNALS\|INFRA_SIGNALS" \
       --include="*.py" .

For each, capture:
  - Where the keywords live
  - How many distinct routes they encode
  - Whether an LLM-router exists alongside (if yes, the heuristic
    is dead code; flag for removal)

Severity:
  P0 — heuristic is the ONLY routing path (no LLM router exists)
  P1 — heuristic and LLM router both exist; heuristic is the
       default — should flip
  P2 — heuristic is fallback; LLM router is primary — fine but
       schedule heuristic deletion

Output: audit_outputs/routing_findings.md, prefix `RT-`.

For each P0, include the proposed migration plan (per
CARSON_PATTERNS.md §8 "migration").

Constraints:
  - Read-only
  - Don't false-positive on access-control checks (those should
    be deterministic, not LLM-based)
```

---

## H. Critic-loop audit

```
@carson-fixer apply AUDIT-CRITIC-LOOP

Goal: assess the quality of the critic / quality-gate pattern
across agents per CARSON_PATTERNS.md §9.

Inspect:

1. Where is the critic implemented?
     grep -rln "critic\|self_review\|grader\|verdict" \
       --include="*.py" agents/ langgraph-system/

2. For each loop using the critic, capture:
   - The MAX_LOOPS value
   - Whether the critic returns multi-dim scores or boolean
   - Whether the directive is fed back as primary-agent input
     on retry, or whether it's just logged
   - Whether scope_respect is one of the scored dimensions

3. Identify retry patterns that don't use a critic:
     grep -rn "retry\|attempt < " --include="*.py" agents/
   Each retry without critic feedback is a finding.

Severity:
  P0 — retry with no critic (loop will spin on the same
       failure mode)
  P1 — critic returns boolean; should be multi-dim scores
  P2 — critic exists but doesn't track scope_respect
  P3 — MAX_LOOPS > 5 (should be ≤ 3 with HITL escalation)

Output: audit_outputs/critic_findings.md, prefix `CRITIC-`.

Constraints:
  - Read-only
  - Test files exempt
  - For each finding, include a sample of recent loop traces
    showing the failure (if available in carson_dashboard's run
    history; if not, mark as "needs trace")
```

---

## I. Naming audit (canonical names + emoji-free)

```
@carson-fixer apply AUDIT-NAMING

Goal: enforce §13, §14, and Invariant 7 of
AGENT_BEHAVIOR_GUARDRAILS.md.

Categories:

1. Legacy agent names still in use:
   For each of these, grep for non-comment occurrences:
     Brandson, Aquiles, Bob, Hydra, Pixie, Studio, CSB, Athena-Dev
   If found, propose the canonical replacement per §13 mapping.

2. Multiple Carson variants:
     grep -rEn "Carson[- ]?(admin|fixer|builder)" \
       --include="*.py" --include="*.md" --include="*.json" \
       --include="*.yaml" --exclude-dir=.venv --exclude-dir=.git .

3. Emoji presence:
     grep -rPn "[\x{1F300}-\x{1FAFF}]|[\x{2600}-\x{27BF}]" \
       --include="*.py" --include="*.md" --include="*.txt" \
       --exclude-dir=.venv --exclude-dir=.git .
   Every hit is a finding (Invariant 7).

4. Cute / playful tone in agent system prompts:
     grep -rEn "Sure!|Absolutely|Let me dive|Let's go|Awesome|Cool" \
       --include="*.py" agents/

Severity:
  P1 — legacy agent names in production code
  P2 — emojis in prompts / outputs (P1 if in user-facing UI text)
  P2 — multiple Carson variants in user-facing strings
  P3 — playful tone in prompts

Output: audit_outputs/naming_findings.md, prefix `NM-`.

Constraints:
  - Read-only
  - Don't flag emojis inside test fixtures that test emoji parsing
  - Don't flag legacy names inside historical CHANGELOG / docs
    that explicitly describe the rename
```

---

## J. Pattern-violation audit

This is the meta-audit: find every place that should have followed
CARSON_PATTERNS.md but rolled its own.

```
@carson-fixer apply AUDIT-PATTERN-VIOLATIONS

Goal: identify code that should have used a canonical pattern from
CARSON_PATTERNS.md but invented a one-off solution.

Per CARSON_PATTERNS.md sections, check:

§1 ChromaDB ingestion:
  - Multiple `chromadb.PersistentClient(...)` calls — there should
    be exactly one canonical caller in carson_kb/ingest.py.
  - Custom chunkers / embedders not in the canonical config.
  - Bespoke ingestion scripts in agents/ or scripts/ folders.

§2 Agent creation:
  - Agent files that don't follow the file/class template.
  - Agents that subclass a non-canonical Agent parent.
  - Agents with inlined BASE_SYSTEM (not loaded via the helper).

§3 MCP tool/server:
  - MCP servers with no `tools.py` separation.
  - Tools without pydantic args / without docstrings.
  - Multiple servers for the same external service.

§4 Registration:
  - Agents not registered (compare files in agents/ vs registry).
  - Manual `KNOWN_AGENTS = [...]` lists in any module.

§8 Routing:
  - Keyword routers (covered by AUDIT-ROUTING).

§9 Critic loop:
  - Retry loops without critics (covered by AUDIT-CRITIC-LOOP).

§10 Autonomous variants:
  - Agents with `supports_autonomous` missing or hardcoded
    `autonomous_phases` in the orchestrator.

For each violation:
  - Cite the exact §X of CARSON_PATTERNS.md it violates
  - Quote the deviation
  - Estimate refactor effort to align with the pattern

Output: audit_outputs/pattern_findings.md, prefix `PAT-`.

Constraints:
  - Read-only
  - If a violation has a documented exemption (e.g., the legacy
    heuristic router during migration), flag it as P3 with the
    deletion deadline noted
```

---

## How to run multiple audits in sequence

For pre-demo cleanup, the recommended order is:

1. `AUDIT-NAMING` — fastest, cheapest, highest cosmetic impact.
2. `AUDIT-HARDCODING` — security/compliance critical.
3. `AUDIT-CONFIRMATION` — behavior critical (per Invariant 1).
4. `AUDIT-MODE-RESPECT` — observability critical.
5. `AUDIT-ROUTING` — sets up the migration off heuristics.
6. `AUDIT-CRITIC-LOOP` — quality of the agent runs.
7. `AUDIT-DUPLICATION` — codebase health.
8. `AUDIT-PERFORMANCE` — last because it usually requires data.
9. `AUDIT-PROMPT-OVERRIDE` — security-adjacent, do before any
   external-facing demo.
10. `AUDIT-PATTERN-VIOLATIONS` — meta-audit, run last to catch
    anything the others missed.

Each produces its own findings file. Once all run, generate a
**combined executive summary** at
`audit_outputs/00_executive_summary.md` per
CARSON_AUDIT_PLAYBOOK.md §11.

Fixes go through the prompts in `CARSON_REFACTOR_PROMPTS.md` —
one cluster PR per area.
