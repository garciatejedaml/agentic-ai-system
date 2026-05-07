# CARSON ATHENA AUDIT — Autonomous Coder + Embedding Pipeline

> Paste-ready audit prompt. Pegalo a Carson (Copilot) tal cual. Read-only. Produce markdown findings under `outputs/athena_audit/`.

---

## MISSION
You are auditing Carson's autonomous coder capability for the Athena Python monorepo and the embedding/retrieval pipeline that supports it. Produce a brutally honest assessment of:
1. What tools the Bob job exposes.
2. Whether Carson can DISCOVER those tools dynamically (this is treated as a first-class concern, not a sub-topic).
3. What state the Athena embedding is in (collections, chunking, metadata, model).
4. A prioritized fix manifest with severities, dependencies, and waves.

This is a READ-ONLY audit. Do NOT modify code, configs, or Chroma collections. Output is markdown only.

---

## SCOPE
- Repo paths: `/credit/**` (Athena monorepo)
- Bob job: `athena_developer_bob_job.py` (or its current name — search for it)
- Chroma DB: locate the active Chroma path used by Carson today
- JIRA integration: locate any existing JIRA client or harvest code (may not exist)
- Memory: `carson_facts` if present

---

## PRE-FLIGHT (P0 — do before any phase)
1. Locate the Bob job file. Print absolute path and total LOC.
2. Locate the Chroma persistence directory. Print path and list all collections with their doc counts and embedding dimensions.
3. Locate `/credit` root. Print top-level subdirectories and approximate file counts.
4. Locate any JIRA client or harvester. Print path or `NOT FOUND`.
5. List every ingestion script (anything that writes to Chroma). Print paths.
6. Locate the tool registration mechanism (Strands `@tool`, MCP, custom registry). Print where tools are registered.

If (1) or (2) cannot be located, STOP and report. Do not guess paths.

---

## PHASE A — BOB JOB ANATOMY
Open the Bob job file and any modules it imports. Capture:
- Agent role / system prompt (verbatim if short, else summary).
- Workflow pattern: deterministic, reactive, LangGraph state machine, plain loop?
- Model used (Sonnet, Haiku, Bedrock model id).
- Entrypoint and main loop.
- HITL gates: where they exist, what triggers them.
- Critic loop: present? boolean or multi-dim? directive feedback?
- State persistence: where sessions, jobs, and traces are written.
- Inputs the job accepts (file paths, ticket ids, prompts).

Output → `outputs/athena_audit/A_bob_anatomy.md`

---

## PHASE B — TOOL INVENTORY & DISCOVERABILITY (TREATED AS FIRST-CLASS)
This phase has TWO parts. Both must be completed.

### B.1 — Tool inventory
Scan the Bob job and all transitively imported modules for tool registrations (`@tool`, `StructuredTool`, MCP server tools, or whatever pattern is in use). For EVERY tool found, capture:

| field | description |
|---|---|
| name | function/method name |
| file:line | absolute path + line of definition |
| docstring | full text |
| params | name, type, default, description |
| returns | type and shape |
| side_effects | read-only / writes files / hits external API / writes Chroma |
| idempotent | yes / no / unknown |
| referenced | listed in some agent's `tools=[...]` or orphaned |

Render as a markdown table sorted by file. Flag any tool with a missing or one-line docstring as `LOW_DISCOVERABILITY`.

Output → `outputs/athena_audit/B1_tool_inventory.md`

### B.2 — Discoverability (the critical question)
Answer each of these explicitly with evidence:

1. Does a tool **registry** exist that an LLM-driven agent can query at runtime? (e.g., a function `list_available_tools()` that returns name + description + params for every tool). If yes, where? If no, mark as P0.
2. Are tools added to agents via **hardcoded lists** (`tools=[t1, t2, t3]`) or via **dynamic discovery** (agent reads registry at session start)? Provide file:line evidence either way.
3. Are tool docstrings written for **LLM consumption** (clear what / when to use / what NOT to use it for) or only for humans? Score 0-3 per tool: 0 = no docstring, 1 = one liner, 2 = describes what, 3 = describes what + when + when-not. Aggregate average.
4. Is there a `describe_capabilities()` tool the agent can call to introspect its own toolbox?
5. If a NEW tool is added (e.g., `extract_jira_chain`), what would Carson have to do to start using it? List the steps. If "code change required", that is the failure mode to fix.
6. Are tools versioned or fingerprinted so Carson can detect when the toolbox has changed since last session? (Most likely no — capture the current state honestly.)

For each question, produce: answer (yes/no/partial), evidence (file:line), impact (what fails because of this), severity (P0–P3).

Output → `outputs/athena_audit/B2_discoverability.md`

---

## PHASE C — EMBEDDING STATE
For the Chroma DB used by Athena retrieval:
- Enumerate all collections. For each: doc count, embedding dimension, embedding model, and creation date if available.
- Sample 5 random docs per collection. Print full metadata for each (NOT the embedding vector).
- Determine chunking strategy. Categorize as: `line_window` / `char_window` / `file_whole` / `function_ast` / `class_ast` / `unknown`.
- Identify the embedding model (Bedrock Titan, Cohere, OpenAI, local). Print version/name.
- Identify the reranker if any. File:line, model, top-k pre and post.
- Identify metadata fields present. Cross-check against this target list and mark each as PRESENT / ABSENT:
  - `file_path`, `symbol_name`, `symbol_kind`, `signature`, `types_in`, `types_out`
  - `callers_count`, `callees_count`, `imports`, `decorators`, `domain`, `role`
  - `hot_score`, `last_commit_msg`, `last_commit_sha`, `last_commit_date`
  - `tactical_why`, `strategic_why`, `business_why`, `regulatory_anchors`
  - `has_tests`, `tests_paths`, `summary` (LLM-generated), `intent`
- Confirm whether multiple views per chunk exist (raw code + summary + structural). Yes/No with evidence.

Output → `outputs/athena_audit/C_embedding_state.md`

---

## PHASE D — ATHENA REPO REALITY CHECK
For `/credit/**`:
- Top-level subdirectories with file count, total LOC, last commit date.
- Hot files: top 20 by churn in last 6 months. Use:
  `git log --since="6 months ago" --pretty=format: --name-only -- credit/ | sort | uniq -c | sort -rn | head -20`
- Regulatory hotspots: grep code AND commit messages for `Basel`, `CCAR`, `SOX`, `FRTB`, `IFRS`, `Dodd-Frank`, `MiFID`. Group hits by subdirectory.
- Type hint coverage estimate: count `def ` declarations vs `def ` declarations followed by `(.*\) -> `. Report ratio per subdirectory. Heuristic only, do not run mypy.
- Test layout: where do tests live (`tests/`, `__tests__/`, alongside source). Sample 3 test files per layout style.
- Identify any `setup.py`, `pyproject.toml`, or `requirements*.txt`. List dependencies relevant to embedding (chromadb, sentence-transformers, openai, anthropic, boto3, langchain, llama-index).

Output → `outputs/athena_audit/D_athena_reality.md`

---

## PHASE E — GAP ANALYSIS
Cross-reference Phases A–D against the target architecture for Athena retrieval. Produce four explicit lists:

### E.1 — MISSING TOOLS
For each missing tool, state: name, why it matters, what currently substitutes for it (if anything), proposed signature.
Target tool set to check against:
- `ast_chunk_file(path) → list[Chunk]`
- `extract_imports(path) → list[Import]`
- `extract_decorators(symbol) → list[Decorator]`
- `extract_type_info(symbol) → TypeProfile`
- `fetch_git_history(path, n=10) → list[Commit]`
- `extract_jira_refs(commit_msg) → list[str]`
- `fetch_jira_ticket(key) → Ticket`
- `walk_jira_parents(key, max_depth=4) → list[Ticket]`
- `summarize_with_haiku(text, fields) → dict`
- `classify_role(symbol) → Role`
- `detect_regulatory_anchors(text) → list[str]`
- `embed_multi_view(chunk) → dict[view → vector]`
- `query_with_filters(text, filters, k=20) → list[Hit]`
- `rerank_with_haiku(query, hits, k=10) → list[Hit]`
- `list_available_tools() → list[ToolSpec]`
- `learn_fact(scope, key, value)`
- `recall_fact(scope, key) → value`

### E.2 — MISSING METADATA
Per absent field from Phase C: name, why it matters, source of truth (where it would come from).

### E.3 — MISSING DISCOVERY
Per gap from Phase B.2: name, what fails today, proposed fix shape (registry pattern, dynamic loading, doc upgrade).

### E.4 — MISSING SAFEGUARDS
Check explicitly:
- PII/secret scan before embedding. PRESENT / ABSENT.
- Compliance flag propagation (regulatory_anchors → HITL trigger). PRESENT / ABSENT.
- Tool side-effect labeling (read vs write vs external). PRESENT / ABSENT.
- Confirmation gate before mutating Chroma. PRESENT / ABSENT.

Output → `outputs/athena_audit/E_gaps.md`

---

## PHASE F — FINDING CARDS
Convert each gap from Phase E into a finding card. Use this EXACT schema:

```
### F-NN — <short title>
- Severity: P0 | P1 | P2 | P3
- Category: tools | metadata | discovery | safeguards | performance
- Evidence: <file:line or "absent">
- Why it matters: <1-2 sentences>
- Proposed fix: <2-4 sentences, concrete and actionable>
- Depends on: <other F-IDs or "none">
- Effort: S (≤1d) | M (2-4d) | L (≥1w)
```

Severity guide:
- **P0** — agent cannot do its job without this; OR compliance/safety blocker; OR data leak risk.
- **P1** — agent works but output is materially low-quality (wrong context, missing impact analysis).
- **P2** — agent works but burns tokens, latency, or human review time unnecessarily.
- **P3** — nice-to-have, future polish.

Output → `outputs/athena_audit/F_findings.md`

---

## PHASE G — FIX MANIFEST (PRIORITIZED ROADMAP)
Sort findings by (severity desc, dependencies satisfied first, effort asc). Group into 3 waves:

- **WAVE 1 (this week)** — every P0 with no unmet dependency, plus P1s that unblock others. Target ≤ 5 days total.
- **WAVE 2 (next 2 weeks)** — remaining P1s, P2s with high impact.
- **WAVE 3 (later)** — P3s and dependency-tail items.

For each wave produce:
- Ordered list of F-IDs.
- Total estimated effort (sum of S/M/L).
- Success criteria (how we know the wave is done — testable bullets).
- Risks (what could derail).

Output → `outputs/athena_audit/G_fix_manifest.md`

---

## PHASE H — TOOL DISCOVERY DESIGN (only if B.2 found discovery is broken)
If Phase B.2 produced a P0 on discovery, write a short design doc proposing the discovery mechanism. Cover:
1. Registry shape (Python dict, JSON file, MCP server, custom).
2. How tools self-register (decorator side effect, manifest file, etc.).
3. How the agent queries at session start.
4. How tool descriptions are surfaced to the LLM (in system prompt as catalog, or queryable on demand).
5. How additions/removals of tools are detected without code changes to the agent.
6. Backward compatibility with existing hardcoded tool lists during migration.

This is a DESIGN doc, not implementation. Output → `outputs/athena_audit/H_discovery_design.md`

---

## CRITICAL INSTRUCTIONS
- Do NOT modify any code, config, or Chroma collection. Read-only.
- Do NOT call external APIs (JIRA, Bedrock) unless the user explicitly approves. If a phase requires it and consent is absent, mark the phase as DEFERRED and continue.
- If you find PII, secrets, credentials, or unredacted client data anywhere, redact in output and raise a separate P0 finding. Do not paste sensitive content verbatim.
- If a phase produces more than 200 lines of evidence, write the long form to its file and emit a 20-line summary inline.
- If you encounter ambiguity about scope, intent, or whether to proceed, STOP and ask the user. Do not assume.
- Do not invent metadata that does not exist. "Absent" is a valid answer and often the correct one.

---

## OUTPUT INDEX
At completion, produce `outputs/athena_audit/00_index.md` with:
- Links to all phase outputs in order.
- Top 5 findings ranked by severity × impact.
- One-paragraph executive summary (max 8 sentences).
- Recommended starting wave + first 3 finding IDs to attack.
- A `READY_TO_FIX` flag: `true` if all P0s have proposed fixes that depend only on local code; `false` otherwise.

Begin Phase 0 (Pre-flight) now.
