# Carson · self-audit playbook

This is **the** playbook Copilot follows to produce a complete audit
of the Carson repo. It is designed to be **run autonomously by
Copilot** with no human in the loop — no clarifying questions, no
shortcuts, no improvisation. Each phase has explicit procedures and
fillable output templates.

The intended output is a folder `audit_outputs/` at the repo root
containing one findings MD per phase plus an executive summary and a
fix manifest.

**Recent context to keep in mind**: agents have been migrated to
**Strands** (AWS-style agent SDK pattern with `@tool` decorators and
agent providers), and a **deterministic vs non-deterministic toggle**
has been introduced to choose between predictable graphs and reactive
agents. These two changes are the highest-value targets for the
audit — they're new, less battle-tested, and easy to mis-wire.

---

## §0. Pre-flight

Before any audit phase, run:

```bash
cd C:\repos\high-touch-agent-prompts
git status
git log -1 --format="%h %s"
git rev-parse --abbrev-ref HEAD
```

Record the SHA and branch in `audit_outputs/00_executive_summary.md`.
Do **not** make any code changes during the audit phase. The audit is
**read-only** — fixes are proposed in the manifest, never applied
directly.

If the working tree is dirty, stop and report: the audit must run
against a known commit.

Create the output folder:

```bash
mkdir audit_outputs
```

Copy the templates from `audit_outputs_templates/` (in this branch,
`claude/carson-audit-2026-04-27`) into `audit_outputs/` and fill them
in as you go.

---

## §1. Phase 0 — Repo map

**Goal**: produce a one-page map of the repo so every later phase has
a navigation index.

**Procedure**:

```bash
# tree (depth-limited) — first, top-level
tree -L 2 -I '.venv|__pycache__|.pytest_cache|node_modules|.git' .

# Lines of code per top-level directory
for d in agents carson_dashboard carson_data confluence-oauth-setup \
         dcd-spec docs langgraph-system mcp-servers mcp-test-harness \
         scripts skills vscode-extension; do
  if [ -d "$d" ]; then
    count=$(find "$d" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.yaml" -o -name "*.yml" \) | xargs -I {} wc -l {} | awk '{s+=$1} END {print s}')
    files=$(find "$d" -type f | wc -l)
    echo "$d: $files files, $count code lines"
  fi
done

# Recently modified files (last 14 days)
find . -type f -name "*.py" -mtime -14 -not -path "./.venv/*" -not -path "./.git/*" | head -40

# Markdown docs in the root
ls -la *.md
```

**Output**: fill in `audit_outputs/01_repo_map.md` with the tree, LOC
table, and the list of recently modified files. Flag any folder that
has > 5K LOC or > 100 files — those are areas the audit should cover
in proportional depth.

---

## §2. Phase 1 — Strands migration audit

**Goal**: characterize how thoroughly the strands migration has
landed and where the half-migrated surfaces are.

**Procedure**:

```bash
# Where is "strands" referenced?
grep -rn "strands\|@tool\|Agent(" --include="*.py" \
     --exclude-dir=.venv --exclude-dir=.git . | head -100 > /tmp/strands_refs.txt

# Which agents have @tool decorators?
grep -rln "@tool" agents/ langgraph-system/ --include="*.py"

# Which agents still use the legacy "BaseAgent" or similar?
grep -rln "class .*Agent.*BaseAgent\|class .*Agent.*ABC" agents/ --include="*.py"

# Inventory: every file in agents/
find agents/ -name "*.py" -type f
```

For each agent file found, **categorize** into one of:

- **strands-native** — uses `Agent(...)`, `@tool`, no legacy base class
- **hybrid** — has both strands hooks and legacy base class
- **legacy** — only the legacy base class, no strands references
- **unknown** — neither pattern matches

**Common issues to capture**:

1. **Mixed paradigms in one agent** — a file that imports both the
   old base class and `strands.Agent`. Resolve to one.
2. **Tool functions without `@tool`** — methods named like tools but
   not exposed via the decorator. Strands won't see them.
3. **Inconsistent provider config** — different agents pointing at
   different model IDs / regions / providers without justification.
4. **Missing system prompts** — strands `Agent(system_prompt=...)`
   sometimes empty or default-stringified. Each agent must have an
   explicit prompt.
5. **Hardcoded model IDs in agent files** — should come from a single
   config file, not be re-typed per agent.
6. **Tool input/output schemas missing types** — strands works best
   with pydantic-typed tool args. Untyped args are runtime
   landmines.

**Severity guide**:

- `P0` — broken: agent won't load, missing imports, type errors
- `P1` — broken at runtime: tool not callable, prompt empty, model ID wrong
- `P2` — works but inconsistent: mixed paradigms, hardcoded values
- `P3` — polish: missing docstrings, weak type hints, naming drift

**Output**: `audit_outputs/02_strands_findings.md` with one finding
card per issue. For each finding:

```
### Finding S-{N}: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Location**: agents/<file>.py:<line>
- **Category**: mixed_paradigms | missing_tool_decorator | hardcoded_model | prompt_empty | other
- **Evidence**:
  ```python
  # <code excerpt showing the issue>
  ```
- **Why it's a problem**: <one paragraph>
- **Proposed fix**:
  ```python
  # <code excerpt showing the fix>
  ```
- **Verification**: <one-line test or grep that confirms the fix>
```

---

## §3. Phase 2 — Deterministic-mode audit

**Goal**: understand how the deterministic toggle is wired and find
the wrong-by-default cases.

**Procedure**:

```bash
# Where is "deterministic" referenced?
grep -rn "deterministic\|non_deterministic\|reactive\|graph_mode" \
     --include="*.py" --include="*.yaml" --include="*.yml" \
     --exclude-dir=.venv --exclude-dir=.git . > /tmp/det_refs.txt

# Configuration: how is it picked?
grep -rn "if.*deterministic\|else.*reactive\|graph_mode ==" --include="*.py" .

# Tests touching the toggle
find . -name "test_*.py" -o -name "*_test.py" | xargs grep -ln "deterministic" 2>/dev/null
```

**Questions to answer in the findings file**:

1. **Where does the flag live?** (Per-agent config? Global env? Per-job at dispatch?)
2. **Who decides which mode for a given user request?** Trace the call
   path from the chat input or Jira webhook all the way to the agent
   run. Document each branch.
3. **What's the default if unspecified?** Document and assess: is the
   default sensible? For example, defaulting to "reactive" means LLM
   decides — higher cost and higher non-determinism. Defaulting to
   "deterministic" means the predefined graph runs even when reactive
   would be smarter.
4. **Is the choice observable?** Does each run log which mode it ran
   in? Without this, debugging production issues is guesswork.
5. **Are there agents that should always be one or the other?** Some
   agents (terraform plan, prod deploy) should never be reactive
   because the steps are non-negotiable. Some agents (open-ended
   investigations) should never be a deterministic graph. Audit each.

**Common issues to capture**:

1. **Toggle in wrong layer** — flag at the chat input level when it
   should be at the dispatch level (or vice versa).
2. **No safe default** — code path that crashes when neither flag is
   set.
3. **Mixed semantics** — `deterministic=True` in one place means "run
   the graph" but in another means "use a low-temperature LLM call".
4. **Untested transitions** — switching from reactive to deterministic
   mid-run; what happens to the in-flight state?
5. **No way to override per request** — flag baked into the agent
   class so the user can't choose.
6. **Cost not captured** — reactive runs cost more LLM tokens; the
   flag should be visible in the cost dashboard's filters.

**Output**: `audit_outputs/03_deterministic_findings.md` with the
trace path documented + one finding card per issue. Include a
sequence diagram (text-art is fine) showing the call path from input
to agent run with the decision points marked.

---

## §4. Phase 3 — Per-agent audit

**Goal**: each of Carson's ~25 agents gets reviewed for prompt
quality, tool surface coverage, and role boundary clarity.

**Procedure**:

```bash
# List every agent file
find agents/ -name "*.py" -type f -not -path "*/__pycache__/*"

# For each, capture: file size, has system_prompt, tool count
for f in $(find agents/ -name "*.py" -type f); do
  size=$(wc -l < "$f")
  has_prompt=$(grep -c "system_prompt" "$f")
  tool_count=$(grep -c "@tool" "$f")
  echo "$f: $size lines, system_prompt=$has_prompt, tools=$tool_count"
done
```

For each agent, fill in this checklist:

- [ ] **Identity**: clear single-sentence "I am the X agent for Y."
- [ ] **Role boundaries**: states what it does NOT do
- [ ] **Tools listed**: every `@tool` has a one-line docstring
- [ ] **Failure modes documented**: what happens on tool error
- [ ] **HITL trigger documented**: when does it ask for human review
- [ ] **Token budget set**: cap on input + output to prevent runaway
- [ ] **Prompt caching enabled** (if Anthropic provider): system
      prompt + tool defs in cache_control blocks
- [ ] **No PII leakage**: tool args sanitized before logging
- [ ] **Test coverage**: at least one test in `tests/` exercises the
      agent end-to-end

**Common issues to capture**:

1. **Prompts that overlap** — two agents both claim to handle
   "deploys" with no boundary
2. **System prompts >2000 tokens** — usually a sign the prompt grew
   organically; refactor into shared sections
3. **Hardcoded paths** in prompts (`I:/repositories/...`) — won't
   work in any other env
4. **Examples dated 2024 or earlier** — the demo year is 2026; old
   examples confuse the model
5. **Reused boilerplate** — same 200-line prefix copy-pasted across
   agents; should be a shared `BASE_SYSTEM` string
6. **Tool count >15** — agent is probably overscoped; consider split
7. **Tool count 0** — agent is just a prompt; consider whether it
   should be a function not an agent

**Output**: `audit_outputs/04_agents_findings.md` with one section
per agent + the consolidated finding cards.

---

## §5. Phase 4 — LangGraph residue audit

**Goal**: find every place the legacy LangGraph orchestrator still
runs, and classify whether it should be removed, kept as a thin
adapter, or rewritten in strands.

**Procedure**:

```bash
# LangGraph imports
grep -rn "from langgraph\|import langgraph\|StateGraph\|MessageGraph" \
     --include="*.py" --exclude-dir=.venv .

# State definitions
grep -rn "class .*State.*TypedDict\|class .*State.*BaseModel" \
     --include="*.py" --exclude-dir=.venv langgraph-system/ agents/

# Conditional edges
grep -rn "add_conditional_edges\|add_edge" --include="*.py" .

# MAX_WORKFLOW_STEPS or similar guards
grep -rn "MAX_WORKFLOW_STEPS\|MAX_STEPS\|max_iterations" --include="*.py" .
```

**Common issues to capture**:

1. **Two orchestrators wrapped around the same agent pool** — the
   classic Carson pre-strands sin. If both still exist, document
   which is the "primary" and what would break if the secondary is
   deleted.
2. **State schema mismatch** — strands `Agent.state` vs LangGraph
   `StateGraph` typed dict. Document divergences.
3. **Deferred consolidation** — TODOs / FIXMEs about merging the
   orchestrators. Capture them; they're shipped tech debt.
4. **Orphaned state fields** — fields written by one orchestrator,
   never read; or read by the other orchestrator with a different
   meaning.
5. **Step counters as runtime guards** — `MAX_WORKFLOW_STEPS = 100`
   suggests an infinite-loop concern. Document the bug it was
   patching and whether strands solves it natively.

**Output**: `audit_outputs/05_langgraph_findings.md`. Include a
table: which agents still touch LangGraph, which fully migrated,
which on hybrid surfaces.

---

## §6. Phase 5 — MCP server audit

**Goal**: each MCP server is a remote tool exposed to agents.
Inspect schemas, auth, error handling, and version pinning.

**Procedure**:

```bash
# List MCP servers
find mcp-servers -maxdepth 2 -type d -not -path "*/__pycache__*"

# Inventory: for each server, its package and entry point
for d in mcp-servers/*/; do
  echo "--- $d ---"
  ls "$d" | head -20
  cat "$d/pyproject.toml" 2>/dev/null | head -30
  cat "$d/README.md" 2>/dev/null | head -20
done

# How are servers registered for agents?
grep -rn "mcp_server\|MCPServer\|tool_set" --include="*.py" .

# Are any tool names colliding across servers?
grep -rh "@tool\|name=\"" mcp-servers/ --include="*.py" | sort | uniq -c | sort -rn | head -30
```

**Common issues to capture**:

1. **Tool name collisions** — two MCP servers exposing a `search()`
   tool. Strands resolves by latest-registered which is fragile.
2. **No timeout on remote calls** — every MCP call should have a
   bounded timeout; without it, an unresponsive Jira drags the whole
   agent down.
3. **Auth scopes too broad** — an agent that should only read Jira
   tickets has write access. Each agent should have a min-perms IAM/
   token scope per MCP.
4. **No retry policy** — transient network errors propagate as full
   failures; should retry with backoff for idempotent reads.
5. **Schemas drift between MCP and strands wrapper** — the MCP server
   says `priority: int`, the strands tool exposes it as `str`. The
   agent will fail at the boundary.
6. **Hardcoded URLs** — `http://confluence.example.com` baked in;
   should come from config.
7. **No version pinning** — MCP server pulled from `latest` instead of
   a tagged release.

**Output**: `audit_outputs/06_mcp_findings.md` with a table per
server (auth method, scopes used, timeout config, retry policy,
version pin) + finding cards.

---

## §7. Phase 6 — Security audit

**Goal**: find every secret leak, credential mis-scoping, and audit
gap.

**Procedure**:

```bash
# Hardcoded URLs / paths / credentials
grep -rEn "http://|https://|I:/repositories|martin@jpmc|F702937|@jpmc\.com" \
     --include="*.py" --include="*.yaml" --include="*.json" \
     --exclude-dir=.venv --exclude-dir=.git . > /tmp/security_strings.txt

# Possible secrets
grep -rEn "api_key\s*=|secret\s*=|password\s*=|token\s*=" \
     --include="*.py" --include="*.yaml" --include="*.yml" \
     --exclude-dir=.venv --exclude-dir=.git . | grep -v "test\|fixture\|mock\|example"

# Are .env / .env.template up to date?
diff .env.template <(awk -F= '{print $1"="}' .env 2>/dev/null) 2>/dev/null

# Any files in .gitignore that nonetheless got committed?
git ls-files | xargs -I {} bash -c 'git check-ignore "{}" 2>/dev/null && echo "{}"' | head -30
```

**Common issues to capture**:

1. **Hardcoded credentials** — even if it's a default test token,
   flag it.
2. **Personal info in fixtures** — names, emails, employee IDs in
   test data that ships with the repo.
3. **Logs that capture full prompts including PII** — agent prompts
   often include user data; the logger should redact.
4. **Unscoped IAM** — an agent that hits AWS using a "human
   developer" role instead of a service-scoped one.
5. **No audit log of state-changing actions** — if an agent merges a
   PR, there must be a row in some audit table. Trace each.
6. **`.env` committed** — shouldn't be there. Check `git ls-files |
   grep "\.env$"`.

**Output**: `audit_outputs/07_security_findings.md` with a redacted
table of every hardcoded credential found, and finding cards for
each issue. **Do not paste actual secret values into the
findings** — replace with `<redacted-NN-chars>` placeholders.

---

## §8. Phase 7 — Observability audit

**Goal**: every agent run, every tool call, every routing decision
must be traceable.

**Procedure**:

```bash
# Logging coverage
grep -rln "logging\|logger\.info\|logger\.error" --include="*.py" agents/ langgraph-system/

# Structured vs print logging
grep -rn "print(" --include="*.py" agents/ langgraph-system/ | head -30

# Token tracking
grep -rn "token_tracker\|input_tokens\|output_tokens\|usage" --include="*.py" .

# OpenTelemetry / X-Ray hooks
grep -rn "opentelemetry\|xray\|trace_id\|span" --include="*.py" .
```

**Common issues to capture**:

1. **`print()` in production code paths** — should be `logger.info`
2. **Token usage tracked in memory only** — never makes it to a
   metrics backend
3. **No correlation ID per agent run** — can't follow a user request
   across the 5 agents that handled it
4. **Missing routing decision logs** — when the router picks agent X
   over agent Y, the reason should be logged
5. **HITL pauses untracked** — the dashboard shows them but they may
   not be in the durable audit log
6. **Errors logged without stack** — `logger.error("failed")` with
   no context is useless

**Output**: `audit_outputs/08_observability_findings.md` with the
coverage matrix + finding cards.

---

## §9. Phase 8 — Data layer audit

**Goal**: the persistence story (RAG collections, ChromaDB, git-sync,
SQLite) needs to be coherent.

**Procedure**:

```bash
# RAG collection definitions
grep -rn "Collection\|chunk_size\|embedding_model" --include="*.py" .

# ChromaDB usage
grep -rn "chromadb\|persist_directory" --include="*.py" .

# SQLite paths
grep -rn "sqlite3\|\.db" --include="*.py" --exclude-dir=.venv .

# Git sync paths
grep -rln "git push\|auto-sync\|carson_data" --include="*.py" --include="*.ps1" .
```

**Common issues to capture**:

1. **Multiple SQLite DB paths in different files** — not pointing at
   the same file
2. **No versioning of RAG collections** — if you change embedding
   models, old chunks become noise
3. **Git sync of conversation logs** — privacy issue (any reader
   sees everyone) + bloat (thousands of commits/month)
4. **No retention policy** — old chunks live forever, dashboard
   slows down
5. **Hot vs cold tier missing** — recent runs in fast storage, old
   runs in archive; today probably all in one place

**Output**: `audit_outputs/09_data_layer_findings.md`.

---

## §10. Phase 9 — Testing audit

**Goal**: assess the test surface area and identify gaps that put
the demo at risk.

**Procedure**:

```bash
# All test files
find . -name "test_*.py" -o -name "*_test.py" | grep -v .venv

# Coverage of agents/
agents_total=$(find agents/ -name "*.py" -not -name "__init__*" | wc -l)
agents_tested=$(find . -name "test_*.py" | xargs grep -l "agents\." 2>/dev/null | wc -l)
echo "Agents: $agents_tested test files referencing $agents_total agent files"

# Pytest config
cat pyproject.toml 2>/dev/null | grep -A 10 "\[tool.pytest"
cat pytest.ini 2>/dev/null
```

**Common issues to capture**:

1. **Strands migration without test updates** — old tests still
   exercising the deleted base class
2. **No integration tests** — every test mocks the LLM; no test
   actually runs against bedrock
3. **No HITL test path** — the approve/reject loop is untested
4. **No deterministic-mode coverage** — both branches of the toggle
   should have at least one test each

**Output**: `audit_outputs/10_testing_findings.md`.

---

## §11. Phase 10 — Synthesis

After all phase findings are written, produce
`audit_outputs/00_executive_summary.md` with:

1. **One-page summary**: 5 bullets covering the most critical
   findings across all phases
2. **Top 10 blockers for the demo** — what would embarrass us if
   it broke during the demo next week
3. **Quick wins** — findings that take < 2h to fix and have high
   visible impact
4. **Strategic debt** — findings that are P0/P1 but require ≥ 1
   sprint to fix; flag for post-demo
5. **Clean-up debt** — P3 findings to batch in a single janitor PR
6. **Risk register** — anything that requires a leadership decision
   (kill an agent, redo the strands migration, etc.)

Also produce `audit_outputs/99_fix_manifest.md`: a flat ordered list
of every finding card across all phases, sorted by severity then by
estimated fix time. This is the doc the engineer or Copilot uses to
plan the fix sprint.

---

## §12. Phase 11 — Fix proposals

For each P0 and P1 finding, write a one-line fix proposal in
`99_fix_manifest.md`. Format:

```
- [ ] [P0] S-04 (agents/aquiles.py:42) — Add `@tool` decorator to
      `_run_tests`. Est: 5 min. Verify: `grep "@tool" agents/aquiles.py | wc -l` returns 8.
```

For P0 findings, **also** include a code patch in the finding card.
For P1, include the patch only if it's < 30 lines. P2/P3 don't need
patches in the finding card — the fix protocol covers them later.

---

## §13. Phase 12 — Verification protocol

Once the fix manifest is generated, the audit phase is **done**.
Fixes are applied separately, **one PR per cluster**:

- Cluster A: all P0 strands findings → 1 PR
- Cluster B: all P0 deterministic findings → 1 PR
- Cluster C: all P0 security findings → 1 PR
- Cluster D: all P1 by-area
- Cluster E: P2 polish, batched per area

Each cluster PR title:
`fix(carson): audit cluster X — <area> · <count> findings`

Each PR description:
- The cluster's finding cards from `99_fix_manifest.md`
- Each finding marked `[x]` after the fix is in the diff
- Verification output (the grep / test command + its result) for
  each card

If any verification fails, **stop**, revert the cluster PR, file the
failed verification as a new P0 finding in a separate audit
follow-up MD.

---

## §14. Hard global constraints

Apply to the entire audit phase, no exceptions:

1. **Read-only.** The audit produces reports, not code changes. Any
   urge to "just fix this real quick" is suppressed.
2. **No file in `carson_dashboard/static/` is touched.** The UI is
   locked.
3. **No file in this branch (`claude/carson-audit-2026-04-27`) is
   modified.** The audit framework is the source of truth — read
   from it, write findings to `audit_outputs/`.
4. **Don't paste secrets into findings.** Redact with
   `<redacted-NN-chars>` placeholders.
5. **One commit at the end of the audit phase.** Title:
   `audit: full repo self-audit · <date>`. The diff is just the
   `audit_outputs/` folder.
6. **If a phase's procedure errors out** (file missing, command
   fails) — record the error in the phase's output MD with a
   `Phase incomplete` banner at the top, and continue with the next
   phase. Don't block the audit on one bad command.

---

## §15. Output schema reference

Every finding card across all phases follows this exact format:

```markdown
### Finding {AREA}-{N}: {one-line title}
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 1-strands | 2-deterministic | 3-agents | 4-langgraph |
             5-mcp | 6-security | 7-observability | 8-data | 9-testing
- **Location**: <file>:<line> (or <file> if file-scope)
- **Category**: <one of the predefined categories per phase>
- **Evidence**:
  ```{lang}
  {code or output excerpt — keep < 30 lines}
  ```
- **Why it's a problem**: {one paragraph}
- **Proposed fix**: {one paragraph or short patch}
- **Estimated fix time**: <X min/h>
- **Verification**: {one-line command that confirms the fix worked}
- **Owner**: {agent name if applicable, else "platform"}
```

Areas:
- `S` — strands
- `D` — deterministic
- `A` — agents
- `L` — langgraph
- `M` — mcp
- `SE` — security
- `O` — observability
- `DA` — data
- `T` — testing

So a strands P0 might be `S-01`, a security P1 might be `SE-04`.

---

## §16. Quick-reference command index

| What | Command |
|------|---------|
| Tree | `tree -L 2 -I '.venv\|__pycache__\|.pytest_cache\|node_modules\|.git'` |
| LOC by language | `find . -name "*.py" -not -path "./.venv/*" \| xargs wc -l \| tail -1` |
| Search code | `grep -rn "<pat>" --include="*.py" --exclude-dir=.venv .` |
| Recently modified | `find . -type f -name "*.py" -mtime -14 -not -path "./.venv/*"` |
| Pytest | `pytest --collect-only` |
| Git who-touched-it | `git log --pretty=format:'%h %an %s' --follow <file>` |
| Show file with line numbers | `cat -n <file> \| less` |
| Diff against branch | `git diff origin/main -- <file>` |

---

## §17. End

When all 10 phases are written and the executive summary + fix
manifest are filed, commit:

```bash
git add audit_outputs/
git commit -m "audit: full repo self-audit · 2026-05-02"
```

Push to a new branch (do NOT push to main or to the dashboard
branch):

```bash
git checkout -b audit/repo-2026-05-02
git push origin audit/repo-2026-05-02
```

Then file a single ticket / chat message to Martin:

> Self-audit complete. Branch `audit/repo-2026-05-02`. Findings:
> X P0, Y P1, Z P2, W P3. Top 3 blockers documented in
> `audit_outputs/00_executive_summary.md`. Fix manifest in
> `audit_outputs/99_fix_manifest.md`.

The audit is done. No fixes have been applied. Wait for direction.
