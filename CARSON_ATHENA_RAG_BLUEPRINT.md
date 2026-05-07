# Carson Athena RAG Blueprint — Context + Architecture + Prompts

> Self-contained handoff doc. Paste into a new Carson/Claude session to pick up where we left off.
> Combines: the architectural decisions for Athena retrieval, the audit prompt, and the safe execution plan.

---

## 0. Context (read first)

**User**: Martin, JPMorgan Chase. Email garciatejedaml@gmail.com.

**System**: Carson — multi-agent AI copilot built on **Strands Agents + LangGraph**, currently runs on Citrix VDI for Athena (the JPMC credit risk Python monorepo). Migration to AWS planned (1-week MVP feasible if AMPS account is reusable).

**Repo branch in use**: `garciatejedaml/agentic-ai-system` -> branch `claude/carson-audit-2026-04-27`.

### Carson's current state (as of last session)

- **14+ specialized agents** named in the form `{capability} agent` (no human names — single Carson identity, no `Carson-admin`/`Carson-fixer` duplicates).
- **Backend**: FastAPI `server.py`, multiple SQLite stores (ops, audit, autonomous, chats, agent_rooms, pm), router, Strands tools, LangGraph workflow.
- **Frontend**: dashboard with views for cost, replay, autonomy, audit, multi-chat, PM, agent rooms (WhatsApp-style with strands trace).
- **Behavioral guardrails** (`AGENT_BEHAVIOR_GUARDRAILS.md`): 8 invariants (ask-before-change, no assumptions, langgraph-routed, no prompt overrides, no hardcoding, surface tradeoffs, professional tone, stop on ambiguity).
- **Pattern docs**: `CARSON_PATTERNS.md` (12 sections), `CARSON_AGENT_TEMPLATES.md` (per-agent templates), `CARSON_AUDIT_PROMPTS.md` (10+ audits), `CARSON_REFACTOR_PROMPTS.md` (14 refactors).

> **Note**: The files listed above (`AGENT_BEHAVIOR_GUARDRAILS.md`, `CARSON_PATTERNS.md`, `CARSON_AGENT_TEMPLATES.md`, `CARSON_AUDIT_PROMPTS.md`, `CARSON_REFACTOR_PROMPTS.md`) are included in this repo alongside this blueprint.
- **Athena ingestion**: ChromaDB local files, embedded `/credit/**` (Python), basic chunking. NO JIRA chain, NO AST chunking, NO multi-view embeddings, NO type info in metadata, NO carson_facts integration.
- **Bob job** (`athena_developer_bob_job.py`): runs autonomous coder operations on Athena, has Strands tools, BUT tool discovery is hardcoded — Carson cannot dynamically introspect available tools.

### Pain points driving this work

1. **Vector RAG over `/credit` returns chunks but loses interdependency context** — a coder agent can't reason about call graphs or impact.
2. **The "why" of code lives in JIRA tickets and their parent chains**, not in code or docstrings — currently invisible to Carson.
3. **The autonomous coder cannot discover new tools** without code changes; adding a tool means modifying the agent.
4. **SDLC autonomous commit flow** (post-review) lacks state machine, retry budget, test-failure parsing, and ticket-comment finalization.
5. **Past attempts to refactor everything in one session broke the system** — no checkpoints, no smoke tests, no rollback.

---

## 1. Target Architecture (Athena retrieval)

### 1.1 — Four retrieval layers (complementary, not alternatives)

| Layer | What | When to use | Cost |
|-------|------|-------------|------|
| **Lexical** | Exact symbol/grep lookup | User names a known symbol | Free, fast |
| **Semantic (vector)** | Natural-language descriptive queries | Discovery ("where do we validate JWT?") | Embedding cost |
| **Structural (graph)** | Call/import/inheritance/test edges | Impact analysis, blast radius | Free (AST) |
| **Documental + historical** | Docstrings, ADRs, git log/blame, JIRA chain | The "why" behind code | JIRA API + Haiku |

Plus a fifth layer:

| Layer | What | When to use |
|-------|------|-------------|
| **Learned (`carson_facts`)** | Repo-specific conventions and decisions the agent has learned | Inject into system prompt when working on that repo |

Persists in DynamoDB or SQLite.

### 1.2 — AST-based chunking (not line-based)

Use **tree-sitter**. Chunk at the function / class / method level. Each chunk gets metadata extracted from the AST:

- `signature` — full function/method signature
- `types_in` — parameter types (from annotations or stubs)
- `types_out` — return type
- `decorators` — `@tool`, `@route`, `@task`, `@deprecated`, etc.
- `imports` — module-level imports used by this chunk

### 1.3 — Multi-view embeddings

Per chunk, embed **three views** into separate OpenSearch (or Chroma) collections:

| View | Content | Good for |
|------|---------|----------|
| **Raw code** | The function body verbatim | Exact code search |
| **Summary** | Haiku-generated 2-3 line summary | "What does X do?" queries |
| **Structural** | Signature + types + caller list + callee list (natural language) | "What calls X?" / "What does X depend on?" |

Query against all three, combine scores, rerank with Haiku.

### 1.4 — History chain harvest (the high-leverage piece)

For each chunk:

1. `git log --follow` -> recent commits that touched the file/symbol.
2. Regex `[A-Z]+-\d+` on commit messages -> JIRA ticket keys.
3. JIRA API -> fetch ticket + parent + grandparent (story -> epic -> initiative).
4. **Filter PII/secrets out of ticket text BEFORE embedding.**
5. Haiku batch summarizer produces three "why" levels per chunk:
   - `tactical_why` (from story)
   - `strategic_why` (from epic)
   - `business_why` (from initiative + linked regulatory drivers)
6. Detect `regulatory_anchors` (Basel III, CCAR, SOX, FRTB, IFRS, Dodd-Frank, MiFID).

Cache JIRA tickets in DynamoDB shared across repos. Refresh delta daily.

### 1.5 — Cross-repo extension (the multiplier)

A single JIRA epic typically touches multiple repos (Athena Python + Terraform + pipelines + configs). Index ticket chain in a shared table + maintain inverted index `ticket_key -> [(repo, file, symbol)]`.

Lets the agent answer:

- "What other repos changed for BASEL-1247?"
- "This regulatory initiative touched these N repos — show all related PRs."
- "Detect orphan PRs across the same ticket."

### 1.6 — Free metadata (no LLM cost)

Extract from existing signals on every chunk:

| Signal | Source | Field |
|--------|--------|-------|
| Type info | mypy/pyright stubs | `types_in`, `types_out` |
| Decorators | AST | `decorators` |
| Imports + dependencies | AST / pydeps | `imports`, `module_deps` |
| Tests-to-source mapping | Convention (`tests/test_foo.py` <-> `foo.py`) | `test_file` |
| Git churn | `git log --shortstat` (6 months) | `churn_score`, `hot_file` |
| Last commit author + message | `git log -1` | `last_author`, `last_commit_msg` |
| Subdirectory taxonomy | Path (`/credit/scoring`, `/credit/decisioning`) | `domain` |

### 1.7 — LLM enrichment pass (one-time, batched, ~USD 50-150 with prompt caching)

Per function/class via Haiku:

| Field | Description |
|-------|-------------|
| `summary` | 2-3 line summary |
| `role` | Closed list: `data_io`, `business_logic`, `model_inference`, `api_endpoint`, `infrastructure`, `utility`, `test_helper`, `deprecated` |
| `risk_flags` | `touches_pii`, `writes_to_db`, `external_call`, `affects_pricing` |
| `intent` | "Why does this exist?" in 1 sentence |

### 1.8 — Tool discovery (CRITICAL — fix the Bob job)

Replace hardcoded `tools=[t1, t2, t3]` with dynamic registry:

- Tools self-register via decorator side effect into a global registry.
- Agent at session start calls `list_available_tools()` to get name + description + params for every tool.
- Tool docstrings written for LLM consumption (what / when / when-NOT-to-use).
- Adding a new tool = drop a `@tool` decorator into the codebase, no agent changes.
- Tools are versioned/fingerprinted so agent can detect toolbox changes between sessions.

---

## 2. The Athena Audit Prompt (paste-ready)

**File on disk**: `CARSON_ATHENA_AUDIT_PROMPT.md`. Read-only audit. Outputs markdown findings under `outputs/athena_audit/`.

### Phases

| Phase | Name | Scope |
|-------|------|-------|
| **0** | Pre-flight | Locate Bob job, Chroma path, `/credit`, JIRA client, ingestion scripts, tool registration mechanism |
| **A** | Bob job anatomy | System prompt, workflow pattern, model, HITL, critic, persistence |
| **B** | Tool inventory + discoverability | Registry exists? Hardcoded vs dynamic? Docstring quality 0-3? `describe_capabilities()` tool? What if a new tool is added? |
| **C** | Embedding state | Collections, chunking strategy, embedding model, reranker, metadata field presence/absence cross-checked vs target list |
| **D** | Athena reality | Top-level subdirs, hot files via 6-month churn, regulatory grep hotspots, type hint coverage, test layout, dependencies |
| **E** | Gap analysis | Missing tools, missing metadata, missing discovery, missing safeguards |
| **F** | Finding cards | Severity P0-P3, category, evidence, fix, depends, effort |
| **G** | Fix manifest | 3 waves with success criteria + risks |
| **H** | Tool discovery design doc | Only fires if Phase B found discovery is broken |

### Constraints

- **Read-only** — no code changes, no Chroma writes
- **No external API calls without consent**
- **PII/secret redaction enforced**
- **Stop-on-ambiguity required**

---

## 3. The Execution Plan (paste-ready)

**File on disk**: `CARSON_EXECUTION_PLAN.md`. Master playbook for running audits + refactors safely.

### Three non-negotiable rules

1. **One wave per Carson session.** Never queue two waves.
2. **`git tag` before each wave**, smoke test after.
3. **If smoke fails, rollback to previous tag** — do NOT patch forward.

### Smoke test (must pass after every wave)

1. Server imports without error.
2. Dashboard boots.
3. Reactive flow: one user message -> agent response with tool call.
4. Deterministic flow: one autonomous job transitions through >=2 states.
5. Agent rooms view loads.
6. ChromaDB query returns >0 hits.
7. `git diff <tag>` shows only the wave's intended scope.

### Wave sequence (9 main + Athena-specific)

| Wave | Name | Risk | Description |
|------|------|------|-------------|
| **0** | Audits (read-only) | None | A-K from `CARSON_AUDIT_PROMPTS.md` + Athena audit. Triage findings before any refactor. |
| **1** | Cosmetic | Low | RENAME (#1), DE-EMOJI (#2). Mechanical, large file count, no logic change. |
| **2** | Config extraction | Low-Med | EXTRACT-CONFIG (#4), LOAD-BASE-SYSTEM (#5). Pulls hardcoded values into config. |
| **3** | Carson consolidation | Medium | CARSON-CONSOLIDATE (#3). Single Carson identity. Risky after Wave 2 leaves no hardcoded refs. |
| **4** | Dedup | Medium | DEDUP (#9). Net deletes from audit B findings. |
| **5** | Routing (HIGHEST RISK) | **High** | LANGGRAPH-ROUTING (#10) -> smoke -> LLM-ROUTER (#6). **Sub-tag between the two.** |
| **6** | Behavior | Medium | CRITIC-LOOP (#7), ASK-BEFORE-CHANGE (#12). Multi-dim critic + HITL guard. |
| **7** | Autonomous + Kerberos | Medium | AUTONOMOUS-VARIANTS (#8), KERBEROS (#13). |
| **8** | Polish | Low | PERFORMANCE (#11), IMPROVE-AGENTS (#14). |
| **9** | SDLC commit flow | Medium | Refactor #15 (not yet written, see section 4.1). |

### Athena waves (parallel after Wave 8)

| Wave | Name | Description |
|------|------|-------------|
| **A0** | Athena audit (read-only) | Run audit phases 0-H |
| **A1** | Fix manifest Wave 1 | Critical fixes from audit findings |
| **A2** | History chain harvester | git -> JIRA -> parents |
| **A3** | Multi-view embeddings + AST chunking | tree-sitter + 3-view embed |
| **A4** | Cross-repo extension | Shared ticket index across repos |

### Stop conditions

- Two consecutive smoke fails
- Diff >3x expected size
- Scope creep into unrequested files
- Unexpected new agent names or paths
- Chroma collection size jumps unrelated to current wave

**Realistic timeline: 5-7 working days total.** Do NOT compress to 1 day — that is what broke it last time.

---

## 4. Pending Work (writing-needed before execution)

### 4.1 — Refactor #15 SDLC-COMMIT-FLOW (not yet written)

**Trigger**: the post-approval autonomous commit flow has multiple transitions (commit -> tests -> possible failures requiring re-changes -> re-tests -> final commit + ticket comment). Today this is implicit/loop-based, no state machine, no retry budget, no test-failure parsing.

The new prompt must specify:

- **Explicit state machine**: `approved -> committing -> testing -> (passed | failed) -> (commenting | retrying)`.
- **Retry budget** with exponential backoff, capped at N attempts.
- **Test failure parser**: which tests failed, line numbers, failure category (assertion / import / runtime / timeout).
- **Critic-loop integration** on retries: second attempt uses feedback from first failure, not regeneration from scratch.
- **HITL escalation** when retry budget exhausted — agent does NOT silently commit broken code.
- **Final state actions**: ticket comment with summary (what was done, what failed and was fixed, what fix was applied) + commit pushed + ticket transitioned to next workflow status.

**Place in plan**: Wave 9. Do not run Wave 9 until prompt is written and reviewed.

### 4.2 — Cross-repo design doc (`CARSON_HISTORY_CHAIN.md`)

Companion to `CARSON_PATTERNS.md`. Covers:

- Per-repo chunker variations (Python AST, Terraform HCL, pipelines, configs).
- Shared `jira_tickets` table schema in DynamoDB.
- Inverted index `tickets_to_chunks` and `initiatives_to_repos`.
- Harvester architecture (delta refresh, rate limiting, PII filter).
- Haiku enrichment prompt with explicit no-PII instruction.
- Integration with `carson_facts` for self-improving metadata.

### 4.3 — AWS migration (separate track, post-Athena cleanup)

> **⚠ FUTURE STATE — NOT CURRENT ARCHITECTURE.** Carson currently runs locally on Citrix VDI with ChromaDB. AWS migration is planned but not yet underway. Do not implement any of the items below until the local architecture is stable and the decision to migrate is made.

- **Layer mapping**: ECS Fargate + ALB + DynamoDB + OpenSearch Serverless + S3 + Bedrock + Secrets Manager.
- **5-tier memory**: L0 in-context, L1 ElastiCache (defer to v2), L2 DynamoDB, L3 OpenSearch, L4 S3.
- **1-week MVP feasible** IF AMPS account is reusable AND Bedrock model access exists. Bottleneck is JPMC compliance review, not code.

---

## 5. How to Use This Doc

### 5.1 — In a fresh Carson/Claude session

Paste sections 0-4 verbatim. Then say:

> "I want to continue from this state. Confirm you understand the architecture in section 1, the audit in section 2, and the execution plan in section 3. Ask me which wave I want to run, then drive that wave's prompt only — do not chain waves."

### 5.2 — Onboarding a teammate

Have them read 0-4 in order. They will know where Carson is, what the target is, and what the safe execution path looks like. Reference docs by filename when concrete details are needed.

### 5.3 — As a planning anchor

Use section 3's wave list as a checklist. Tag each wave's start/done in git. Maintain `outputs/cleanup_log.md` with one entry per wave.

---

## 6. What NOT to Do (post-mortem of past failure)

- Do NOT run multiple refactor prompts in a single session expecting they'll compose cleanly.
- Do NOT skip smoke tests because "it looked fine in the diff".
- Do NOT run Wave 5 (routing) without Waves 1-4 stable for at least 24h.
- Do NOT bundle prompt 10 + prompt 6 in Wave 5 — sub-tag between them.
- Do NOT touch ChromaDB collections during a non-Athena wave.
- Do NOT let Carson invent new agent names or new file paths that weren't asked for — this is scope creep and a stop condition.
- Do NOT keep secrets/PATs in chat history. If a token is pasted by mistake, revoke it immediately.

---

## 7. Open Questions (decide before relevant wave)

1. **JIRA credentials for Bob job?** If no, Wave A2 (history chain harvest) is blocked until they're provisioned.
2. **MCP for GitHub authenticated?** If no, Wave 9 SDLC commit flow needs a fallback (file-based patch) until OAuth is restored.
3. **Bedrock model access on AMPS** — Claude Sonnet 4.6 + Haiku 4.5 enabled? If no, AWS week-1 plan slips ~1 week per Bedrock approval ticket.
4. **Athena ingestion scheduled or manual?** If scheduled, Wave A2/A3 must coordinate with cron to avoid mid-run mutation.
5. **PII/secret scanning library approved at JPMC?** Macie / Comprehend / internal? This decision blocks Wave A2.

---

## 8. Relationship to Other Carson Docs

| Document | Relationship |
|----------|-------------|
| `CARSON_AUDIT_FIXES.md` | The 17 Tier 1-4 fixes for `high-touch-agent-prompts` (LangGraph version). This blueprint supersedes the RAG-specific fixes with a more comprehensive architecture. |
| `CARSON_DASHBOARD.md` | Dashboard v2 spec. This blueprint's tracing architecture (section 1.4) feeds into the dashboard's Trace view. |
| `CARSON_COPILOT_STRATEGY.md` | Copilot integration strategy. Complementary — Copilot is the IDE client, this blueprint improves what Carson knows. |
| `AMPS_SLOW_CONSUMER_REFACTOR_PROMPT.md` | AMPS performance fix. Separate concern but same infrastructure (AWS account reuse question). |
| `CARSON_SELF_IMPROVEMENT_EXECUTION.md` | The Tier 1 execution prompt. This blueprint's Wave 0-8 sequence is the evolved version of the tier-based approach. |
| `CARSON_PATTERNS.md` | 12 architectural patterns. This blueprint adds pattern #13 (multi-view retrieval) and #14 (history chain harvest). |
| `AGENT_BEHAVIOR_GUARDRAILS.md` | 8 behavioral invariants. This blueprint respects all 8; Wave 6 strengthens #1 (ask-before-change) and #7 (critic loop). |

---

## 9. Architecture Evolution Summary

The Carson system has evolved significantly from the initial `high-touch-agent-prompts` LangGraph setup:

| Aspect | Before (LangGraph-only) | Current (Strands + LangGraph) |
|--------|-------------------------|-------------------------------|
| Agent framework | LangGraph with Bedrock | Strands Agents + LangGraph workflow |
| Agent naming | Human names (Mr. Brandson, Jenkins, etc.) | Capability names (`git agent`, `build agent`) |
| Agent count | 20 in config.yaml | 14+ specialized |
| Dashboard | Basic Streamlit concept | 130KB monolith with cost/replay/autonomy/audit/multi-chat/PM/agent-rooms views |
| Storage | ChromaDB + config.yaml | Multiple SQLite stores (ops, audit, autonomous, chats, agent_rooms, pm) |
| Tools | MCP servers per agent | Strands `@tool` decorator + MCP servers |
| Identity | Multiple Carsons (admin, fixer) | Single Carson identity |
| RAG | Basic chunking, line-based | Target: AST-based, multi-view, history-enriched |
| Guardrails | Implicit | Explicit 8-invariant doc |
| Execution safety | None (broke on multi-refactor) | Wave-based with git tags + smoke tests |
