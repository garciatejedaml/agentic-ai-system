# Carson Multi-Agent System — Self-Improvement Audit & Execution Prompt

> **Purpose**: This document is a comprehensive prompt that Carson (using Opus 4.6 in Copilot mode) can execute against its own codebase to systematically identify and fix issues across the entire multi-agent system.
>
> **How to use**: Open this file in VS Code Copilot with Opus 4.6, select the entire content, and instruct the model: *"Execute this audit against the high-touch-agent-prompts repo. Apply all fixes you can, and create a report of what was changed and what needs human review."*

---

## PHASE 0: CONTEXT LOADING

Before making any changes, read and internalize:

```
READ agents/*.agent.md          # All 24 agent definitions
READ langgraph-system/config.yaml  # Routing + orchestration config
READ langgraph-system/carson_service.py  # Core orchestration engine (75KB monolith)
READ mcp-servers/*/server.py    # All 19 MCP server implementations
READ skills/*/                  # All skill reference files
READ .env.template              # Environment variable definitions
READ README.md                  # System overview
```

Build a mental map of:
1. Which agents exist and what each one does
2. Which MCP tools each agent claims to have access to
3. Which skills each agent references
4. The routing keywords each agent defines
5. The safety rules each agent enforces

---

## PHASE 1: ANTI-HALLUCINATION AUDIT

### 1.1 MCP Tool Existence Validation

**Problem**: Agent files reference MCP tools that may not exist in the actual MCP server implementations. This causes the model to hallucinate tool calls that will fail at runtime.

**Action**:
```
FOR EACH agents/*.agent.md:
  EXTRACT all tool names from the "MCP Tools Available" table
  FIND the corresponding mcp-servers/*-mcp-server-python/server.py
  VERIFY each tool name exists as an actual @tool or @mcp.tool() decorated function
  
  IF tool referenced in agent BUT missing from server:
    FLAG as CRITICAL: "Agent [X] references tool [Y] but it does not exist in [Z] server"
    FIX: Either remove from agent file OR implement in server
    
  IF tool exists in server BUT not listed in agent:
    FLAG as WARNING: "Tool [Y] exists in server [Z] but agent [X] doesn't list it"
    FIX: Add to agent's tool table if relevant
```

**Common hallucination patterns to check**:
- `query_knowledge_base` — verify it exists in the RAG/ChromaDB integration
- `get_code_context` — verify implementation
- Tool names with typos or inconsistent casing (e.g., `list_bob_jobs` vs `query_bob_jobs`)
- Tools referencing deprecated API endpoints

### 1.2 Skill Reference Validation

**Problem**: Agents reference skill files that may not exist or have been moved/renamed.

**Action**:
```
FOR EACH agents/*.agent.md:
  EXTRACT all paths from "Skill References" section
  VERIFY each path exists under skills/
  
  IF path does not exist:
    FLAG: "Agent [X] references skill [path] which does not exist"
    FIX: Find correct path or remove stale reference
```

### 1.3 RAG Collection Validation

**Problem**: Agents reference RAG collections that may not be populated or may be stale.

**Action**:
```
FOR EACH agents/*.agent.md:
  EXTRACT collection names from "RAG Collections" section
  CHECK langgraph-system/chroma_db/ for corresponding collections
  CHECK langgraph-system/*_docs_cache/ folders for source documents
  
  IF collection referenced but empty or missing:
    FLAG: "Agent [X] references RAG collection [name] but it has no documents"
```

### 1.4 URL Validation

**Problem**: Agents embed hardcoded URLs (especially Bob, Jenkins, Spinnaker, Confluence) that may be outdated or point to decommissioned services.

**Action**:
```
FOR EACH agents/*.agent.md:
  EXTRACT all URLs (http/https patterns)
  CATEGORIZE as internal (jpmchase.net) vs external
  FLAG any URL that:
    - Points to a hostname not in .env.template
    - Uses HTTP instead of HTTPS for internal services
    - Contains hardcoded port numbers that should be configurable
    
  FIX: Replace hardcoded URLs with references to environment variables where possible
```

### 1.5 Cross-Agent Referral Validation

**Problem**: Some agents say "suggest routing to [X] agent" but the referenced agent may not exist or may have been renamed.

**Action**:
```
FOR EACH agents/*.agent.md:
  FIND all references to other agents (e.g., "route to Datadog agent", "suggest Build agent")
  VERIFY the referenced agent exists in agents/
  VERIFY the referenced agent's keywords would actually match the routing scenario
```

---

## PHASE 2: ROUTING IMPROVEMENT AUDIT

### 2.1 Keyword Overlap Analysis

**Problem**: With 24 agents, keyword overlap causes routing ambiguity. The router may send requests to the wrong specialist.

**Action**:
```
COMPILE a master keyword-to-agent mapping:
  FOR EACH agents/*.agent.md:
    EXTRACT "Keywords That Route to You" section
    BUILD map: keyword → [list of agents that claim it]

IDENTIFY CONFLICTS:
  FOR EACH keyword:
    IF claimed by MORE THAN ONE agent:
      FLAG: "Keyword '[X]' is claimed by agents: [A, B, C]"
      ANALYZE which agent should truly own it
      FIX: 
        - Remove keyword from non-primary agents
        - Add disambiguation instructions to router/planner
        - Add "When NOT to use this agent" section clarifying boundaries
```

**Known high-risk overlaps to check**:
- "terraform" → terraform.agent.md vs terraform-compat.agent.md vs amps.agent.md
- "deploy" / "deployment" → deploy.agent.md vs spinnaker/build references
- "monitor" / "alert" / "metrics" → datadog.agent.md vs amps.agent.md
- "documentation" / "docs" → docs.agent.md vs confluence references
- "ticket" / "issue" → jira.agent.md vs snow.agent.md (ServiceNow)
- "build" / "pipeline" → build.agent.md vs sdlc.agent.md
- "code" / "branch" / "commit" → git.agent.md vs sdlc.agent.md

### 2.2 Agent Boundary Clarity

**Problem**: Some agents have overlapping domains without clear delineation, causing the planner (Monsieur Planchet) to make incorrect routing decisions.

**Action**:
```
FOR EACH pair of potentially overlapping agents:
  COMPARE their:
    - Domain descriptions
    - MCP tools (are there shared tools?)
    - Keywords
    - Example scenarios
    
  ADD or IMPROVE "When NOT to Activate" sections:
    - Every agent should explicitly list scenarios that LOOK like they belong
      to them but should go elsewhere
    
  Example fix for git.agent.md:
    "## When NOT to Route Here
    - SDLC workflow questions (commit/bless/push pipeline) → route to sdlc agent
    - Branch policies and restrictions → route to sdlc agent  
    - Build status of a branch → route to build agent"
```

### 2.3 Planner (Monsieur Planchet) Enhancement

**Problem**: The planner file (monsieur-planchet.agent.md) at 2.23KB is dangerously lean for orchestrating 24 agents. It lacks:
- Complete agent catalog with capabilities
- Routing decision tree
- Error recovery patterns
- Timeout handling

**Action**:
```
ENHANCE monsieur-planchet.agent.md with:

1. FULL AGENT REGISTRY TABLE:
   | Agent | Domain | Primary Tools | Triggers | Anti-Triggers |
   |-------|--------|---------------|----------|---------------|
   (one row per agent)

2. MULTI-STEP PLAN TEMPLATES for common workflows:
   - Feature development: Jira → Git → Build → SDLC → Deploy
   - Incident investigation: Datadog → Build → Git → Jira
   - Infrastructure change: Terraform → Git → SDLC → Deploy
   - Documentation update: Docs → Git → SDLC

3. ERROR RECOVERY:
   - If agent A fails, which agent B can provide fallback?
   - If user question spans multiple domains, what's the decomposition strategy?
   - Maximum chain depth (prevent infinite routing loops)

4. ROUTING DECISION TREE:
   - First-pass keyword matching
   - Disambiguation questions to ask the user
   - Confidence threshold below which to ask for clarification
```

### 2.4 Carson Concierge Routing Rules

**Problem**: In Full Mode, Carson (the concierge) must decide whether to route via `carson_orchestrate` tool or handle directly. The rules for this decision are vague.

**Action**:
```
IN carson.agent.md, ADD explicit routing rules:

## Routing Decision Matrix

| Request Pattern | Route To | Reasoning |
|----------------|----------|-----------|
| Single-domain, read-only | Direct to specialist | No multi-step needed |
| Multi-domain | Planchet (planner) | Needs decomposition |
| Ambiguous domain | Ask user to clarify | Prevent misrouting |
| System admin task | carson-admin | Only admin can modify system |
| Greeting/chitchat | Handle directly | No specialist needed |
| "I need help with..." | Analyze keywords → route | Standard flow |
```

---

## PHASE 3: COPILOT MODE IMPROVEMENTS

### 3.1 copilot-instructions.md Audit

**Problem**: In Copilot Mode, the VS Code Copilot reads `copilot-instructions.md` to understand which MCP tools to call directly (no LangGraph). This file must be perfectly synchronized with agent capabilities.

**Action**:
```
READ copilot-instructions.md (or .github/copilot-instructions.md)
VERIFY:
  1. Every MCP server listed is actually available and configured
  2. Tool names match exactly what the MCP servers expose
  3. No hallucinated tool names or deprecated tools
  4. Safety rules from individual agents are consolidated here
  5. The routing keywords/decision logic is present for direct dispatch
```

### 3.2 Copilot Mode Safety Parity

**Problem**: In Full Mode, safety is enforced by the LangGraph orchestration layer (which can intercept writes). In Copilot Mode, safety relies entirely on the prompt instructions. Any gap = risk.

**Action**:
```
COMPILE safety rules from ALL agents:
  FOR EACH agents/*.agent.md:
    EXTRACT "Safety Rules" section
    
CREATE a unified safety matrix:
  | Operation Type | Required Confirmation | Agent | Mode |
  |---------------|----------------------|-------|------|
  | Read data     | None (auto-approve)  | ALL   | Both |
  | Create branch | User confirmation    | Git   | Both |
  | Push code     | NEVER (human only)   | SDLC  | Both |
  | Approve/Bless | NEVER (human only)   | SDLC  | Both |
  | Delete branch | User confirmation    | Git   | Both |
  | Create ticket | User confirmation    | Jira  | Both |
  | Deploy        | NEVER (human only)   | Deploy| Both |
  | Modify infra  | NEVER (human only)   | TF    | Both |

VERIFY this matrix is enforced in copilot-instructions.md
```

### 3.3 Copilot Tool Mapping

**Problem**: Copilot Mode skips the router/planner and directly calls MCP tools. If the model doesn't know which tool belongs to which domain, it may call the wrong tool.

**Action**:
```
IN copilot-instructions.md, ensure there is a clear tool→domain mapping:

## Available MCP Servers and Their Tools

### jira-mcp-server (Jira Operations)
- search_issues: Search Jira issues with JQL
- get_issue: Get issue details by key
- create_issue: Create new issue (⚠️ requires user confirmation)
- update_issue: Update issue fields (⚠️ requires user confirmation)
...

### bitbucket-mcp-server (Git/Bitbucket Operations)  
- createBranch: Create a new branch (⚠️ requires user confirmation)
- listBranches: List branches
...

(repeat for ALL 19 MCP servers)
```

---

## PHASE 4: PROMPT ENGINEERING BEST PRACTICES (Anthropic-Level)

### 4.1 Structured Output Enforcement

**Problem**: Agents may generate free-form responses when structured output would be more useful and less prone to hallucination.

**Action**:
```
FOR EACH agents/*.agent.md:
  IN the "Response Style" section, ADD explicit output format templates:
  
  Example for Jira agent:
  "When displaying ticket info, ALWAYS use this format:
   
   ## [TICKET-KEY]: [Title]
   **Status**: [status] | **Assignee**: [name] | **Sprint**: [sprint]
   **Priority**: [priority] | **Type**: [type]
   
   ### Description
   [first 500 chars of description]
   
   ### Recent Activity
   [last 3 comments/transitions]"
   
  This prevents the model from hallucinating fields or inventing data.
```

### 4.2 Chain-of-Thought Enforcement for Complex Decisions

**Problem**: The planner (Planchet) and router make routing decisions without explicit reasoning, increasing misrouting risk.

**Action**:
```
ADD to monsieur-planchet.agent.md:

## Planning Protocol

Before executing any multi-step plan, you MUST:

1. **ANALYZE** the request in <thinking> tags:
   - What domains does this touch? (list them)
   - What is the dependency order?
   - Are there any safety-critical steps?

2. **PLAN** in explicit steps:
   Step 1: [Agent] → [Action] → [Expected output]
   Step 2: [Agent] → [Action] → [Expected output]
   ...

3. **VALIDATE** before execution:
   - Does each step have a clear success/failure criteria?
   - Are write operations gated by user confirmation?
   - Is there a rollback path if step N fails?

4. **EXECUTE** one step at a time, confirming results before proceeding.
```

### 4.3 Grounding Instructions (Anti-Hallucination Core)

**Problem**: Models hallucinate when they lack grounding instructions. Each agent should explicitly state what to do when it doesn't know something.

**Action**:
```
ADD to EVERY agents/*.agent.md a standardized section:

## Grounding Rules

1. **NEVER invent data**: If a tool call returns an error or empty result, say so.
   Do NOT fabricate plausible-looking data (ticket numbers, branch names, URLs).

2. **NEVER guess tool parameters**: If you're unsure of the correct parameter
   value (e.g., project key, branch name), ASK the user.

3. **Cite your source**: When presenting data, always indicate which tool 
   provided it. Example: "According to `query_bob_jobs`..."

4. **Acknowledge limitations**: If your RAG knowledge base or skills don't 
   cover the user's question, say: "I don't have specific documentation on 
   this. Let me check with [alternative source/agent]."

5. **No stale data**: If information might be outdated (cached RAG data),
   prefer live tool calls over RAG knowledge. Only fall back to RAG when 
   tools are unavailable.

6. **Timestamp all data**: When showing build statuses, ticket states, or 
   deployment info, include when the data was fetched.
```

### 4.4 System Prompt Size Optimization

**Problem**: Some agent files are very large (sdlc=13KB, bob=11KB, jira=10KB). Large prompts waste context window and can cause the model to "forget" early instructions.

**Action**:
```
FOR EACH agent file > 8KB:
  ANALYZE what content is:
    a) ESSENTIAL for routing and behavior (keep in agent file)
    b) REFERENCE material (move to skills/ files)
    c) EXAMPLES that could be fewer (reduce to 2-3 key examples)
    
  REFACTOR:
    - Move detailed domain knowledge to skills/ (queryable via RAG)
    - Keep agent file focused on: identity, tools, safety, routing keywords
    - Target: agent files under 5KB each
    
  Example for bob.agent.md (11KB):
    - Core Concepts (procfile types, job states, tags) → skills/bob/bob_reference.md
    - Troubleshooting flows → skills/bob/bob_troubleshooting.md
    - Keep in agent: persona, tool table, safety rules, response format, keywords
```

### 4.5 Consistent Agent File Schema

**Problem**: Agent files don't follow a strict schema. Some have sections others lack. This inconsistency confuses the model.

**Action**:
```
DEFINE and ENFORCE this canonical schema for ALL .agent.md files:

# [Name] — [Role Title]

[1-2 sentence identity/persona description]

## Personality
- [3-5 bullet traits]

## Your Domain
- [What this agent covers]

## MCP Tools Available
| Tool | When to Use |
|------|-------------|

## Skill References
- [paths to skill docs]

## RAG Collections (if applicable)
- [collection names and descriptions]

## Safety Rules
- READ operations: [auto/confirm]
- WRITE operations: [confirm/never]
- [domain-specific rules]

## Grounding Rules  ← NEW MANDATORY SECTION
[anti-hallucination instructions]

## When to Route Here
- [keywords and scenarios]

## When NOT to Route Here  ← NEW MANDATORY SECTION
- [anti-patterns, common confusion with other agents]

## Response Style
[output format templates]

## Keywords That Route to You
- [keyword list for router]
```

---

## PHASE 5: FULL MODE (LANGGRAPH) SPECIFIC IMPROVEMENTS

### 5.1 carson_service.py Decomposition Plan

**Problem**: The orchestration engine is a 75KB monolithic Python file. This is unmaintainable and error-prone.

**Action**:
```
DECOMPOSE into modules:

langgraph-system/
  carson_service.py          → carson_main.py (entry point, <5KB)
  carson_agents/
    agent_registry.py        # Agent loading and registration
    agent_router.py          # Keyword matching and routing logic
    agent_executor.py        # Individual agent execution
  carson_orchestration/
    planner.py               # Multi-step plan execution
    synthesizer.py           # Response synthesis from multiple agents
  carson_rag/
    knowledge_base.py        # ChromaDB integration
    document_loader.py       # Skill/doc ingestion
  carson_tools/
    mcp_bridge.py            # MCP server communication
    tool_registry.py         # Available tool catalog
  carson_safety/
    permission_checker.py    # Read/write/never permission enforcement
    audit_logger.py          # Action logging for compliance
```

### 5.2 Router Confidence Scoring

**Problem**: The router picks an agent based on keyword matching without any confidence score. There's no mechanism to detect low-confidence routes.

**Action**:
```
IMPLEMENT in the routing logic:

1. Score each candidate agent (0.0 to 1.0) based on:
   - Keyword match count / total keywords in request
   - Exact match vs partial match weighting
   - Historical routing accuracy (if tracked)

2. Decision rules:
   - Score > 0.8: Route directly
   - Score 0.5-0.8: Route but include confidence note to agent
   - Score 0.3-0.5: Ask user to clarify ("Did you mean X or Y?")
   - Score < 0.3: Route to general.agent.md as fallback

3. Log all routing decisions for later analysis
```

### 5.3 Agent Response Validation

**Problem**: After an agent responds, there's no validation that the response actually addresses the user's question. The agent might hallucinate an answer.

**Action**:
```
ADD a response validation step in the orchestration:

AFTER agent produces response:
  1. CHECK: Does response reference actual tool calls made? (not invented data)
  2. CHECK: Does response address the original question?
  3. CHECK: Are any URLs in the response valid (match known patterns)?
  4. CHECK: Are ticket numbers, branch names etc. consistent with tool output?
  
  IF validation fails:
    - Flag to user: "⚠️ This response may contain unverified information"
    - Offer to re-query with different parameters
```

---

## PHASE 6: AGENT CONSOLIDATION RECOMMENDATIONS

### 6.1 Merge Candidates

**Problem**: 24 agents is too many. Each additional agent increases routing confusion and prompt overhead.

**Recommended merges**:

```
1. terraform.agent.md + terraform-compat.agent.md → terraform.agent.md
   Reason: Same domain, split is unnecessary. Add compat notes as a section.

2. gossip.agent.md → EVALUATE FOR REMOVAL
   Reason: What does "gossip" agent do? If it's team updates, merge into general.
   
3. picasso.agent.md → EVALUATE scope
   Reason: Diagram generation is a tool, not a full agent domain.
   Consider merging into docs.agent.md or general.agent.md.

4. teams.agent.md → Consider merging with general.agent.md
   Reason: Teams notifications is a single tool, not a full domain.

TARGET: Reduce from 24 to 16-18 focused agents.
```

### 6.2 Missing Agent Analysis

**Problem**: There are skills folders without corresponding agents and vice versa.

**Action**:
```
COMPARE:
  agents/*.agent.md  →  agent names
  skills/*/           →  skill folder names

  Skills WITHOUT agents: guardian, diagram, cbb(?)
  Agents WITHOUT skills: gossip, picasso, teams, monsieur-planchet

  DECIDE for each:
    - Create the missing agent/skill
    - OR remove the orphaned folder
    - OR document why the asymmetry is intentional
```

---

## PHASE 7: PLUGIN & EXTENSION IMPROVEMENTS

### 7.1 VS Code Extension (carson-extension) Audit

```
READ vscode-extension/carson-extension/
VERIFY:
  - Extension correctly loads copilot-instructions.md
  - MCP server connections are properly configured
  - Error handling for disconnected MCP servers
  - User notification when a server is unavailable
```

### 7.2 MCP Server Standardization

**Problem**: 19 MCP servers likely have inconsistent error handling, logging, and response formats.

**Action**:
```
FOR EACH mcp-servers/*/server.py:
  CHECK:
    1. Uses mcp_common/ shared utilities (if it exists)
    2. Returns consistent error format: {"error": "message", "code": "ERROR_CODE"}
    3. Has proper timeout handling
    4. Logs tool calls for debugging
    5. Returns metadata with results (timestamp, source, confidence)
    
  STANDARDIZE error responses across all servers
```

### 7.3 Sync Scripts Improvement

**Problem**: `sync-skills.ps1` and `sync-to-root.ps1` are manual processes that can get forgotten.

**Action**:
```
ADD to scripts/:
  - pre-commit hook that validates agent file schema
  - CI check that verifies skill references exist
  - CI check that verifies MCP tool references match implementations
  - auto-sync on git hook (not manual PowerShell)
```

---

## PHASE 8: EXECUTION CHECKLIST

When running this prompt, execute phases in order and track progress:

- [ ] Phase 1: Anti-hallucination audit complete
  - [ ] 1.1 MCP tool validation
  - [ ] 1.2 Skill reference validation
  - [ ] 1.3 RAG collection validation
  - [ ] 1.4 URL validation
  - [ ] 1.5 Cross-agent referral validation
- [ ] Phase 2: Routing improvements
  - [ ] 2.1 Keyword overlap analysis
  - [ ] 2.2 Agent boundary clarity
  - [ ] 2.3 Planner enhancement
  - [ ] 2.4 Carson routing rules
- [ ] Phase 3: Copilot mode improvements
  - [ ] 3.1 copilot-instructions.md audit
  - [ ] 3.2 Safety parity check
  - [ ] 3.3 Tool mapping verification
- [ ] Phase 4: Prompt engineering best practices
  - [ ] 4.1 Structured output templates
  - [ ] 4.2 Chain-of-thought enforcement
  - [ ] 4.3 Grounding rules added to ALL agents
  - [ ] 4.4 Large agent files refactored
  - [ ] 4.5 Consistent schema enforced
- [ ] Phase 5: Full mode improvements
  - [ ] 5.1 Decomposition plan documented
  - [ ] 5.2 Router confidence scoring designed
  - [ ] 5.3 Response validation designed
- [ ] Phase 6: Agent consolidation
  - [ ] 6.1 Merge candidates reviewed
  - [ ] 6.2 Missing agent/skill gaps resolved
- [ ] Phase 7: Plugin & extension improvements
  - [ ] 7.1 VS Code extension audited
  - [ ] 7.2 MCP server standardization
  - [ ] 7.3 Sync scripts improved

---

## APPENDIX A: KNOWN ISSUES FROM INITIAL AUDIT

These issues were identified during the architectural review and should be prioritized:

1. **carson_service.py monolith (75.72KB)** — Single point of failure, impossible to test individual components
2. **chroma_db/ and *_docs_cache/ in git** — Binary/generated data should be in .gitignore
3. **guardian skill exists but no guardian.agent.md** — Orphaned skill folder
4. **PowerShell-only sync scripts** — Limits contributors to Windows environments
5. **No schema validation for .agent.md files** — Typos and missing sections go undetected
6. **.env.template exposes configuration structure** — Verify no secrets leaked
7. **24 agents with overlapping domains** — Routing confusion inevitable
8. **Planner (2.23KB) too lightweight** for orchestrating 24 specialists
9. **No integration tests** for agent routing accuracy
10. **autonomous_jobs/ folder** — Needs safety review for any jobs running without human oversight

## APPENDIX B: AGENT INVENTORY REFERENCE

| Agent | File | Size | Domain | MCP Server |
|-------|------|------|--------|------------|
| Billy (AMPS) | amps.agent.md | 2.39KB | AMPS messaging | amps-mcp-server |
| Bob | bob.agent.md | 11.03KB | Batch scheduler | bob-mcp-server |
| Build (Jenkins) | build.agent.md | 6.68KB | CI/CD builds | jenkins-mcp-server |
| Carson Admin | carson-admin.agent.md | 2.81KB | System admin | N/A (meta) |
| Carson | carson.agent.md | 4.12KB | Concierge/router | langgraph-mcp-server |
| CBB | cbb.agent.md | 4.57KB | CBB platform | N/A |
| Rocky (Datadog) | datadog.agent.md | 7.26KB | Monitoring | datadog-mcp-server |
| Deploy (Spinnaker) | deploy.agent.md | 4.22KB | Deployments | spinnaker-mcp-server |
| Docs (Confluence) | docs.agent.md | 8.69KB | Documentation | confluence-mcp-server |
| General | general.agent.md | 3.16KB | General/fallback | engineers-docs-mcp |
| Mr. Brandson (Git) | git.agent.md | 6.08KB | Git/Bitbucket | bitbucket-mcp-server |
| Gossip | gossip.agent.md | 2.61KB | Team updates | teams-mcp-server? |
| Hydra | hydra.agent.md | 4.36KB | Hydra platform | N/A |
| Jira | jira.agent.md | 10.05KB | Issue tracking | jira-mcp-server |
| Planchet (Planner) | monsieur-planchet.agent.md | 2.23KB | Orchestration | N/A (meta) |
| Picasso | picasso.agent.md | 2.89KB | Diagrams | diagram-mcp-server |
| Pixie | pixie.agent.md | 4.97KB | Pixie platform | N/A |
| Postman | postman.agent.md | 4.92KB | API testing | N/A |
| M. Contrôle (SDLC) | sdlc.agent.md | 13.24KB | Code promotion | sdlc-mcp-server |
| Snow | snow.agent.md | 5.63KB | ServiceNow | snow-mcp-server |
| Studio | studio.agent.md | 5.15KB | Studio platform | N/A |
| Teams | teams.agent.md | 2.06KB | MS Teams | teams-mcp-server |
| Terraform Compat | terraform-compat.agent.md | 2.74KB | TF Enterprise compat | tfe-mcp-server |
| Terraform (Inspector) | terraform.agent.md | 4.11KB | Infrastructure | tfe-mcp-server |

---

## APPENDIX C: CONCRETE AUDIT FINDINGS FROM config.yaml (6.66KB, 203 lines)

**Full file audit completed April 13, 2026** — Every line read and analyzed.

### C.1 Architecture Overview (What config.yaml reveals)

The config.yaml is the **brain** of the LangGraph system. It defines:
- Team identity (AHTW = AWS High Touch Workflow)
- LLM model selection and routing model
- Agent enable/disable flags
- RAG/ChromaDB collection definitions
- Performance tuning parameters
- Feedback/quality system (Le Critique)

### C.2 LLM Configuration — FINDINGS

| Parameter | Value | Assessment |
|-----------|-------|------------|
| Main model | `anthropic.claude-3-5-sonnet-20241022-v2:0` | **OK** — Good choice for agent work |
| Routing model | Haiku 4.5 via inference profile | **GOOD** — Cost-optimized at ~$0.001/request |
| Embedding model | Bedrock inference profile | **OK** — Verify it's Titan or Cohere |
| temperature | 0.0 | **GOOD** — Deterministic for tool operations |
| max_tokens | 4096 | **WARNING** — May be too low for complex multi-step responses; consider 8192 for planner |

**Critical finding**: The routing uses Haiku 4.5 which is smart cost optimization. But verify the routing_model_arn actually resolves to Haiku 4.5 — the inference profile ID `k4yvmctvgxzy` needs validation against AWS Bedrock console.

### C.3 Agent Registry — MISMATCH ANALYSIS

Config.yaml defines **20 agents** (lines 69-118), but Appendix B lists **24 agents**. Cross-referencing:

**Agents in config.yaml (20):**
jira, git, build, deploy, terraform, terraform_compat, docs, general, amps, snow, postman, picasso, bob, hydra, cbb, pixie, studio, sdlc + (carson, carson-admin are implicit as orchestration layer)

**Agents in Appendix B (24):**
All above + gossip, datadog, teams, monsieur-planchet

**CRITICAL FINDINGS:**
1. **`datadog` is MISSING from config.yaml** — Rocky (Datadog agent) is in the .agent.md files but NOT enabled in config.yaml. This means in Full Mode, Datadog queries may never route correctly.
2. **`gossip` is MISSING from config.yaml** — Either intentionally disabled or forgotten.
3. **`teams` is MISSING from config.yaml** — MS Teams agent not enabled.
4. **`monsieur-planchet` not in agents section** — This is expected since Planchet is the planner node, not a routable agent. But it should be documented.

**ACTION REQUIRED:** Add `datadog: enabled: true` to config.yaml if Rocky is meant to be active. Same for gossip and teams if they should be routable.

### C.4 Agent Categories — DESIGN OBSERVATION

Config.yaml distinguishes two agent tiers (line 106):
1. **Tool-equipped agents** (jira, git, build, deploy, terraform, docs, etc.) — Have MCP tools
2. **Knowledge-only agents** (bob, hydra, cbb, pixie, studio, sdlc) — "No MCP tools"

**FINDING:** The comment says "knowledge-only, no MCP tools" for bob, hydra, cbb, pixie, studio, sdlc. But:
- **sdlc.agent.md (13.24KB)** references `sdlc-mcp-server` in Appendix B. Is it tool-equipped or knowledge-only? This is a **contradiction**.
- **bob.agent.md** lists `query_bob_jobs`, `build_bob_url`, etc. in its tool table. Are these real MCP tools or RAG-based?

**ACTION:** Reconcile the comment on line 106 with actual MCP server existence. If these agents DO have MCP servers, remove the misleading comment. If they DON'T, remove fake tool tables from their .agent.md files.

### C.5 RAG/ChromaDB Configuration — DETAILED FINDINGS

**Persistence:** `persist_dir: "./carson_kb"` (line 122) — ChromaDB persists in a local directory. This means:
- Data is lost if the container/VM is rebuilt
- No shared state across multiple Carson instances
- **RECOMMENDATION:** Consider S3-backed persistence for production

**Team scoping:** `team_id: "ahtw"` (line 125) — Good multi-tenancy design for future teams

**Global Collections (4):**

| Collection | Description | Source | Doc Count | Assessment |
|-----------|-------------|--------|-----------|------------|
| modules | ATLAS Terraform modules | atlasterraform | 5,631 | **LARGE** — Good coverage |
| engineers_docs | JPMC Engineers Docs | engineers_docs | 3,036 | **OK** — AWS patterns & guides |
| amps_core | AMPS official docs | manual | N/A | **WARNING** — "manual" source means manually ingested PDFs; may be stale |
| bundle_matrix | TF module bundle compat | manual | 51 | **SMALL** — Good but verify freshness |

**Team Collections (3):**

| Collection | Description | Source | Assessment |
|-----------|-------------|--------|------------|
| repo_code | AHTW repo code | team_repos (1,868 docs) | **GOOD** — Auto-ingested from repos with extensions filter |
| ahtw_confluence | AWS High Touch Workflow | confluence (page 3688936888) | **OK** — Auto-ingested from Confluence |
| bhtw_confluence | Bond High Touch Workflow | confluence (page 2533782496) | **OK** — Auto-ingested |

**FINDINGS:**
1. **`max_rag_context_tokens: 2000`** (line 180) — This is **very conservative**. Only 2K tokens of RAG context injected per query. For complex terraform questions needing multiple module docs, this may be insufficient. Consider 4000-6000.
2. **No `operation_model` collection** — Confluence page 2538506858 (Operating Model) is defined in `confluence_pages` but has no corresponding RAG collection. Either add it or document why it's excluded.
3. **`repo_code` extensions filter** includes `.py, .md, .yaml, .yml, .xml, .tf, .json` — **Missing `.hcl`** (HashiCorp Configuration Language). If any TF repos use `.hcl` files, they won't be ingested.
4. **No staleness/refresh mechanism** — Config has no `refresh_interval` or `last_updated` for collections. How often is ChromaDB refreshed? Manual process = stale data risk.

### C.6 Performance Tuning — FINDINGS

| Parameter | Value | Assessment |
|-----------|-------|------------|
| max_tokens | 4096 | **Borderline** — OK for simple queries, tight for multi-step plans |
| temperature | 0.0 | **Good** — Deterministic |
| max_tool_iterations | 5 | **OK** — Prevents infinite loops but may be low for complex workflows |
| max_workflow_steps | 100 | **Good** safety limit |
| critique_max_retries | 3 | **Good** |
| enable_prompt_caching | true | **Excellent** — Uses Anthropic's cache_control |
| truncate_tool_results | 8000 | **OK** — 8K chars for tool output |
| max_rag_context_tokens | 2000 | **LOW** — See C.5 finding |
| llm_timeout | 120s | **OK** — 2 min for LLM call |
| mcp_tool_timeout | 30s | **OK** — 30s for tool execution |
| credential_refresh_timeout | 120s | **OK** — PCL login can be slow |

### C.7 Feedback System (Le Critique) — FINDINGS

- `critique_mode: "knowledge_only"` — Le Critique only evaluates knowledge-only agents, NOT tool agents. This means tool agents (jira, git, build, etc.) responses are **never quality-checked**. 
- **RECOMMENDATION:** Consider `critique_mode: "always"` or at least add basic validation for tool agent responses (e.g., did the tool call succeed? Does the response match the tool output?)
- `min_quality_score: 7` — Good threshold (0-10 scale)
- `collect_user_feedback: true` — Good for learning

### C.8 Service Configuration

- `host: "0.0.0.0"`, `port: 8765` — Standard FastAPI service
- `mcp_servers_path: "../mcp-servers"` — MCP servers are in a **sibling directory** to langgraph-system. This means the repo structure is:
  ```
  high-touch-agent-prompts/
    langgraph-system/   (carson_service.py, config.yaml, etc.)
    mcp-servers/        (19 MCP server implementations)
    agents/             (24 .agent.md files)
    skills/             (skill reference docs)
  ```

### C.9 Bitbucket Projects Configuration

Two projects configured:
1. **ACAMPS** — Primary application repos (5 specific repos listed)
2. **CREDITTECH** — Shared repos (`repositories: []` = all repos in project)

**FINDING:** The `default_bitbucket_project: "ACAMPS"` is good for defaulting, but the CREDITTECH project with `repositories: []` means ALL repos in CREDITTECH are accessible. Verify this is intentional security-wise.

### C.10 Deploy Pipeline Mapping

```
branch_to_pipeline:
  "feature/": "dev"
  "develop": "uat"  
  "main": "pre"
```

**FINDING:** No production pipeline mapping. `main` maps to "pre" (pre-production). This is **correct for safety** — production deployments should require additional manual steps. But document this explicitly in the deploy agent.

---

## APPENDIX D: PRIORITY ACTION ITEMS (from concrete audit)

### P0 — Critical (Fix Immediately)
1. **Add `datadog: enabled: true`** to config.yaml agents section (line ~103) — Rocky agent exists but is invisible to the router
2. **Reconcile knowledge-only vs tool-equipped** discrepancy for sdlc, bob, etc. (C.4 finding)
3. **Add `.hcl` to repo_code extensions** filter (line 149) — Missing Terraform HCL files

### P1 — High Priority
4. **Increase `max_rag_context_tokens`** from 2000 to 4000+ (line 180)
5. **Add `operation_model` RAG collection** — Confluence page defined but no collection created
6. **Add `gossip` and `teams`** to config.yaml if they should be routable agents
7. **Consider `critique_mode: "always"`** — Tool agent responses should also be quality-checked

### P2 — Medium Priority
8. **Increase `max_tokens`** from 4096 to 8192 for planner/complex agents
9. **Add RAG refresh mechanism** — No auto-refresh configured for collections
10. **Document the `main → pre` pipeline mapping** explicitly in deploy agent
11. **Sync `config_template.yaml` with `config.yaml`** — Template only has 7 agents vs 20 in config, missing 5+ sections (see Appendix G)

### P3 — Low Priority / Enhancement
12. **S3-backed ChromaDB persistence** for production resilience
13. **Add monitoring for routing confidence** — Log routing decisions and scores
14. **Validate Bedrock inference profile ARNs** against AWS console

### P0.5 — Critical NEW (from April 13, 2026 deep-read session #2)
15. **Add error handling to `send_carson_reply.py`** — No try/except around OutlookCOMClient calls; silent failures possible
16. **Fix `fix_chromadb.py` empty config** — Script passes `config={}` to CarsonKnowledgeBase, bypassing runtime config; should load from config.yaml
17. **Move hardcoded email** `martin.garciatejeda@jpmchase.com` from `send_carson_reply.py` to config.yaml as `default_reply_email`

### P1.5 — High Priority NEW
18. **Upgrade model** — config_template.yaml references `claude-sonnet-4-20250514` but config.yaml still uses Sonnet 3.5 (`20241022-v2:0`). Evaluate upgrade path.
19. **Add `default_bitbucket_project`** and **`is_execution_role`** fields to config.yaml — present in template but missing from active config
20. **Verify `scripts/onboarding.py` exists** — Referenced in config_template.yaml line 5 but not yet validated

---

## APPENDIX E: fix_chromadb.py AUDIT (1.61KB, 54 lines)

**Full file read April 13, 2026**

### Purpose
CLI utility to detect and repair broken ChromaDB collections. Supports `--dry` flag for preview mode.

### Architecture
```
fix_chromadb.py
  └─ imports CarsonKnowledgeBase from carson_agents.rag.knowledge_base
  └─ Instantiates: CarsonKnowledgeBase(persist_dir="./carson_kb", config={})
  └─ Calls: kb.health_check() → {"healthy": [...], "broken": {...}}
  └─ For healthy: kb._get_client().get_collection(name).count() → doc count
  └─ For broken: kb.repair_broken_collections(dry_run=False) → deletes
  └─ Post-repair: "Re-ingest to restore: python -m carson_agents.kb_auto_ingest"
```

### FINDINGS
1. **Empty config `{}`** — The script passes no config, so CarsonKnowledgeBase may use different defaults than runtime. Could miss collections defined in config.yaml.
2. **Uses private method `_get_client()`** — Fragile coupling to internal API; should use public interface.
3. **No automatic re-ingestion** — After deleting broken collections, user must manually run `python -m carson_agents.kb_auto_ingest`. Should auto-recover or at least prompt.
4. **Reveals `carson_agents.kb_auto_ingest` module exists** — This is the ingestion entry point. Carson should audit this module for ingestion logic.
5. **No logging** — Uses `print()` statements only. Should use Python logging for operational use.

---

## APPENDIX F: send_carson_reply.py AUDIT (2.11KB, 85 lines)

**Full file read April 13, 2026**

### Purpose
"Carson Email Reply Helper" — Simple script for Copilot to send email replies via Outlook COM automation.

### Architecture
```
send_carson_reply.py
  └─ Adds ../mcp-servers/outlook-mcp-server-python to sys.path
  └─ imports OutlookCOMClient from source.com_client
  └─ def send_reply(session_id, topic, response, user_email=None) → bool
  └─ Default email: martin.garciatejeda@jpmchase.com (hardcoded)
  └─ Subject format: "[Carson:{session_id}] Re: {topic}"
  └─ Body template: "🤖 Carson AI Butler\n{response}\n---\nSession: {sid}\nTime: {ts}\nSent via Carson (Copilot Mode)"
  └─ client.send_email(to_address, subject, body, is_html=False)
  └─ CLI: python send_carson_reply.py <session_id> <topic> "<response>"
```

### FINDINGS
1. **Hardcoded default email** — `martin.garciatejeda@jpmchase.com` should be in config.yaml as `default_reply_email` or pulled from environment.
2. **No error handling** — No try/except around `OutlookCOMClient()` or `client.send_email()`. COM failures will crash silently.
3. **Windows-only** — Depends on Outlook COM automation, tightly coupled to Windows VDI environment. Not portable.
4. **Session ID format** — Example: `20260403_F702937_vscode_carsonadmin` reveals naming: `{date}_{workstation}_{client}_{user}`.
5. **Confirms Copilot Mode pathway** — This is the bridge between Carson LangGraph system and VS Code Copilot extension. The Copilot agent calls this script to send email replies.
6. **`is_html=False`** — Sends plain text only. Consider HTML formatting for richer responses (tables, code blocks).

---

## APPENDIX G: config_template.yaml vs config.yaml DISCREPANCY ANALYSIS

**Full comparison completed April 13, 2026**

config_template.yaml: 104 lines, 3.46KB (authored 31 Mar 2026)
config.yaml: 203 lines, 6.66KB (authored 13 Apr 2026 — 5 hours ago)

### G.1 Fields in Template but MISSING from config.yaml

| Field | Template Line | Template Value | Impact |
|-------|---------------|----------------|--------|
| `default_bitbucket_project` | 28 | `"YOUR_PROJECT"` | May cause "no default project" errors if code expects this field |
| `is_execution_role` | 42 | `false` | AWS IAM role type not specified in config — may affect credential refresh |
| `repo_to_app_map` | 67 | `{}` | Spinnaker app mapping exists in template but not config |
| `terraform_app_suffix` | 70 | `""` | Terraform suffix for Spinnaker not in config |

### G.2 Sections in config.yaml but MISSING from Template

| Section | Config Lines | Description | Template Impact |
|---------|-------------|-------------|-----------------|
| `confluence_pages` | 14-32 | AHTW, BHTW, operation_model page definitions | New teams won't know to set up Confluence pages |
| `aws` | 34-37 | AWS role ARN and region | Critical for Bedrock — template has it under `llm:` but not as separate section |
| `routing_model_arn` | 60-63 | Haiku 4.5 for cost-optimized routing | New teams will use main model for routing (expensive) |
| `embedding_model_arn` | 64-65 | Bedrock embedding model | No embedding config in template |
| `performance` | 169-189 | max_tokens, temperature, timeouts, caching | **CRITICAL OMISSION** — New teams get no performance tuning |
| `feedback` | 194-202 | Le Critique system config | **CRITICAL OMISSION** — Quality system not in template |

### G.3 Agent Registry Mismatch (Template vs Config)

**Template agents (7):** jira, git, build, deploy, terraform, docs, general

**Config agents (20):** jira, git, build, deploy, terraform, terraform_compat, docs, general, amps, snow, postman, picasso, bob, hydra, cbb, pixie, studio, sdlc

**Missing from template (13):** terraform_compat, amps, snow, postman, picasso, bob, hydra, cbb, pixie, studio, sdlc + (datadog, gossip, teams also missing from both)

### G.4 RAG/ChromaDB Mismatch

| Aspect | Template | Config | Gap |
|--------|----------|--------|-----|
| `enabled` | `false` | Implied true (extensive config) | Template discourages RAG by default |
| Extensions | `[".py", ".md"]` | `[".py", ".md", ".yaml", ".yml", ".xml", ".tf", ".json"]` | Missing 5 extensions |
| Collections | 2 (repo_code, confluence_docs) | 7 (4 global + 3 team) | Missing global_collections/team_collections split |
| `team_id` | Not present | `"ahtw"` | Multi-tenancy not in template |

### G.5 Anthropic Direct API Option

Template line 47 references `claude-sonnet-4-20250514` as the Anthropic direct model. Config.yaml uses Sonnet 3.5 (`anthropic.claude-3-5-sonnet-20241022-v2:0`) via Bedrock. This suggests a model upgrade is planned or available but not yet deployed. **Evaluate Sonnet 4 upgrade for improved agent reasoning.**

### G.6 Onboarding Script Reference

Template line 5: `# Run: python scripts/onboarding.py for an interactive setup.`

This implies an interactive onboarding wizard exists in `scripts/onboarding.py`. **TODO:** Verify this script exists and audit its logic for config generation correctness.

---

## APPENDIX H: FOLDER STRUCTURE OBSERVATIONS (langgraph-system/)

**Observed April 13, 2026 via Bitbucket browse**

### Directories (13):
```
autonomous_jobs/    — Autonomous/scheduled job definitions
bob_docs_cache/     — Bob agent knowledge cache
carson_agents/      — Python package: agents, RAG, tools
carson_kb/          — ChromaDB persistence directory
cbb_docs_cache/     — CBB agent knowledge cache
chroma_db/          — Possibly alternate ChromaDB storage? (vs carson_kb)
docs/               — Documentation
hydra_docs_cache/   — Hydra agent knowledge cache
pixie_docs_cache/   — Pixie agent knowledge cache
scripts/            — Utility scripts (incl. onboarding.py?)
sdlc_docs_cache/    — SDLC agent knowledge cache
studio_docs_cache/  — Studio agent knowledge cache
tests/              — Test suite
```

### Files (11):
```
.carson-pids.json        75 B    — Process ID tracking
.env.example            798 B    — Environment variable template
_launcher.ps1           494 B    — PowerShell launcher
_start_carson_temp.ps1  482 B    — Temp startup script
carson_service.py     75.72 KB   — ** MAIN MONOLITH ** (FULLY AUDITED — see Appendix I)
config.yaml            6.66 KB   — Team config (FULLY AUDITED)
config_template.yaml   3.46 KB   — Config template (FULLY AUDITED)
fix_chromadb.py        1.61 KB   — ChromaDB repair tool (FULLY AUDITED)
pyproject.toml          210 B    — Python project metadata
requirements.txt        434 B    — Python dependencies
send_carson_reply.py   2.11 KB   — Email reply helper (FULLY AUDITED)
```

### Key Observations:
1. **chroma_db/ vs carson_kb/** — Two directories that might both relate to ChromaDB storage. Config uses `persist_dir: "./carson_kb"`. The `chroma_db/` folder may be legacy or for a different purpose. **Investigate.**
2. **One `*_docs_cache/` per knowledge agent** — bob, cbb, hydra, pixie, sdlc, studio each have a cache dir. This suggests they pre-cache knowledge at startup.
3. **`carson_service.py` at 75.72KB is the biggest file** — This is the monolith that needs to be audited next. Key patterns to search: `StateGraph`, `add_node`, `add_edge`, `conditional_edge`, routing functions.
4. **Commit messages** reveal: "Datadog agent (Rocky), Bitbucket fix, ChromaDB fixes, extension installer, .gitignore cleanup" — confirms Rocky/Datadog was recently added (5 hours ago) but still missing from config.yaml agents section.
5. **`autonomous_jobs/` folder** — Autonomous job capability exists but hasn't been audited. May contain scheduled tasks for auto-ingestion, monitoring, etc.

### REMAINING AUDIT BACKLOG (Not Yet Read):
- `carson_service.py` (75.72KB) — **CRITICAL**: Graph construction, routing, node definitions, MCP loading
- `carson_agents/` package — Agent implementations, RAG module, tools
- `scripts/` folder — Onboarding, ingestion, utilities
- `tests/` folder — Test coverage
- `autonomous_jobs/` — Scheduled tasks
- `requirements.txt` / `pyproject.toml` — Dependencies
- `chroma_db/` contents — Verify vs carson_kb/
- `../mcp-servers/` (19 servers) — Individual MCP implementations

---

---

## APPENDIX I: carson_service.py AUDIT (75.72KB, ~1700 lines, 54 functions)

**Full file audit via Ctrl+F raw view — April 13, 2026**

### Purpose
"Carson Service — Flask HTTP server for the multi-agent system" (v2.1.0). This is NOT the LangGraph — it is a Flask HTTP wrapper that delegates to `carson_agents.workflow.get_workflow()` for graph execution. **`StateGraph` appears 0 times** in this file; the actual graph topology lives in the `carson_agents` package.

### I.1 Architecture Overview
```
carson_service.py
  ├─ PROXY CONFIG: http://proxy.jpmchase.net:10443 (HTTPS_PROXY, HTTP_PROXY, NO_PROXY)
  ├─ KERBEROS: PYMETA_PROFILE = 'local' for Jira MCP Server
  ├─ IMPORTS:
  │   ├─ carson_agents.config → load_config, get_llm_config, get_rag_config
  │   ├─ carson_agents.workflow → get_workflow, reset_workflow_counter
  │   ├─ carson_agents.orchestrator → get_orchestrator, _get_llm_plan
  │   ├─ carson_agents.llm → create_llm_client
  │   ├─ carson_agents.conversation_history → get_conversation_history, get/set_current_ticket, get_current_user
  │   ├─ carson_agents.rag.knowledge_base → CarsonKnowledgeBase
  │   ├─ carson_agents.worker → JobManager, WorkerAgent, JiraScanner
  │   ├─ carson_agents.persistence → init_persistence, get_persistence
  │   ├─ carson_agents.shared_state → set_job_manager, set_worker_agent, set_persistence
  │   ├─ carson_agents.headquarters → init_headquarters
  │   ├─ carson_agents.guardian_agent → init_guardian
  │   └─ source.com_client (outlook MCP) → OutlookCOMClient
  ├─ BLUEPRINTS (modularized endpoints):
  │   ├─ carson_agents/blueprints/hq_bp.py → Headquarters endpoints
  │   ├─ carson_agents/blueprints/guardian_bp.py → Guardian endpoints
  │   └─ carson_agents/blueprints/actions_bp.py → Action Relay endpoints
  └─ STARTUP (def main):
      ├─ load_config() → sys.exit(1) if FileNotFoundError
      ├─ ChromaDB Protection: backup() → health_check() → auto-repair broken
      ├─ Graceful shutdown: signal(SIGINT/SIGTERM) + atexit
      ├─ init_headquarters() → auto-commit / git sync every 5 min
      ├─ init_guardian(Path("./conversations")) → cross-VDI monitoring every 60s
      ├─ Phoenix: DISABLED (ASCode issues)
      ├─ create_llm_client() → early credential check
      └─ app.run(host, port=8765, threaded=True)
```

### I.2 Two Execution Paths

**Path A — Single Agent (default):**
```
/ask → get_workflow() → workflow.invoke(initial_state) → response
  └─ LLM router (Haiku 4.5) selects agent
  └─ force_agent parameter bypasses router
```

**Path B — Orchestrator ("Strands-like Multi-Agent"):**
```
/orchestrate → get_orchestrator() → orchestrator.run(request, user_sid, session_id, jira_ticket) → response
  └─ Supervisor Agent plans → invokes sub-agents dynamically
  └─ Human-in-the-loop: status "waiting_for_human" + orchestrator.approve(thread_id)
  └─ Plan format: ["jira", "coding", "git", "build", "deploy"]
  └─ Thread IDs: "orch_20260408_123456"
```

**Orchestrator Trigger Logic (3 conditions, OR'd):**
1. Global `USE_ORCHESTRATOR` flag
2. `force_orchestrator` from request body (`"orchestrate": true`)
3. `_is_multi_step_request(user_request)` — keyword heuristic:
   - Counts domain mentions: jira, git, build, deploy, code
   - If 2+ domains mentioned → orchestrator
   - Also checks for "then" keyword (sequential actions)

### I.3 LangGraph State Schema (13 fields)
```python
initial_state = {
    "user_request": full_request,          # With context prepended
    "intent": None,                        # Set by LLM router
    "current_agent": None,                 # Which agent handles
    "messages": [],                        # Accumulated messages
    "context": data.get("context", {}),    # External context from caller
    "agent_response": None,                # Current agent output
    "final_response": None,                # Final output
    "confirmation_required": None,         # Human-in-the-loop gate
    "confirmed": None,                     # User confirmation
    # Planning fields — MUST be initialized for LangGraph state merge
    "plan": {},
    "plan_steps_completed": [],
    "plan_current_step": 0,
    "plan_done": False,
    "needs_planning": False,
    "original_request": None,
}
```

### I.4 Full API Surface (28+ endpoints — docstring only lists 6!)

**Core:** `/ask` (POST), `/ask/async` (POST), `/health` (GET), `/` (GET)
**Jobs:** `/job/<id>` (GET), `/jobs` (GET)
**Worker:** `/worker/status`, `/worker/start`, `/worker/submit`
**Orchestrator:** `/orchestrate` (POST), `/orchestrate/approve` (POST), `/orchestrate/status` (GET)
**Email/Teams:** `/email/session`, `/email/check`, `/email/reply`, `/email/teams`
**Actions:** `/actions/queue`, `/actions/pending`, `/actions/history`
**RAG:** `/ingest` (POST)
**CRUD:** `/confirm` (POST), `/ticket`, `/conversations` (GET), `/user` (GET)
**Monitoring:** `/dashboard`, `/observability`, `/guardian/status`, `/features`, `/notifications`
**Auth:** `/refresh-credentials` (POST)

### I.5 FINDINGS

1. **75KB monolith with 54 functions** — Blueprint modularization is partially started (hq_bp, guardian_bp, actions_bp) but main endpoints (/ask, /orchestrate, /health, /ingest) still live in this file. Complete the migration.

2. **Dual context system (code smell):**
   - Persistent: `history.get_context_for_llm(session_id, max_messages=6)`
   - Legacy in-memory: `conversation_history` list with `h['a'][:200]` truncated answers
   - Both concatenated into `full_request`. The legacy system should be removed — it's redundant and truncates context to 200 chars.

3. **Orchestrator trigger heuristic is fragile:**
   - `_is_multi_step_request()` uses simple keyword counting — "What's the deploy status of the build?" would trigger orchestrator (matches both "deploy" and "build" domains) even though it's a simple status query for a single agent.
   - RECOMMENDATION: Use the LLM router for orchestration detection too, or add negative patterns.

4. **Docstring lists 6 endpoints, actual count is 28+** — Massive documentation drift. The index endpoint (`GET /`) returns the full list, but the file header comment is dangerously wrong.

5. **Flask dev server in production:** `app.run(threaded=True)` — Not gunicorn/uwsgi. Fine for VDI single-user, but won't scale. Comment says "threaded=True so /health responds instantly even while /ask is processing" — this is the right call for Flask dev server.

6. **ChromaDB startup protection is GOOD (supersedes fix_chromadb.py):**
   - Step 1: `_kb.backup()` before touching anything
   - Step 2: `_kb.health_check()` → auto-repair broken collections with `dry_run=False`
   - BUT `fix_chromadb.py` duplicates this with WORSE config (empty `{}` vs `config.get("llm", {})`)
   - RECOMMENDATION: Delete `fix_chromadb.py` or make it import the startup logic.

7. **`user_sid` defaults to "unknown"** — No authentication layer. Any request without user_sid gets "unknown" identity. Fine for VDI single-user, but security risk if exposed.

8. **Scattered imports:** Functions re-import modules inside their bodies (e.g., `from carson_agents.orchestrator import get_orchestrator` appears in multiple functions). Should be top-level imports with lazy initialization pattern.

9. **Module topology revealed:** 15+ sub-modules in `carson_agents` package:
   - config, workflow, orchestrator, llm, conversation_history, rag.knowledge_base
   - worker (JobManager, WorkerAgent, JiraScanner), persistence, shared_state
   - headquarters, guardian_agent, blueprints (hq_bp, guardian_bp, actions_bp)
   - **Key audit targets:** `workflow.py` (contains actual StateGraph), `orchestrator.py` (Strands-like supervisor)

10. **Phoenix DISABLED:** Comment says "was causing issues with ASCode". Dead code left in place. Either fix and re-enable, or remove entirely.

11. **Jira ticket auto-detection:** Regex `r'\b([A-Z][A-Z0-9]+-\d+)\b'` extracts ticket IDs from user messages. Smart feature but could match false positives (e.g., "AWS-SDK" or "ISO-9001").

12. **Background subsystem orchestration:**
    - HQ: auto-commit + git sync (every 5 min)
    - Guardian: cross-VDI monitoring (every 60s)
    - JobManager: 3 worker threads for async processing
    - WorkerAgent: starts paused, enable via `/worker/start`
    - JiraScanner: disabled by default
    - All gracefully shutdown via signal handlers + atexit

### I.6 Corrected Decomposition Plan (updating Phase 5.1)

The existing Phase 5.1 decomposition proposal assumed `carson_service.py` contains the LangGraph. It doesn't. The real decomposition should be:

```
CURRENT STATE:
  carson_service.py (75KB) = Flask HTTP + endpoints + job processing + startup
  carson_agents/workflow.py = Actual LangGraph StateGraph (NOT YET AUDITED)
  carson_agents/orchestrator.py = Strands-like supervisor (NOT YET AUDITED)
  carson_agents/blueprints/ = Partial modularization (3 blueprints)

RECOMMENDED:
  carson_service.py → carson_main.py (<10KB entry point + startup)
  carson_agents/blueprints/ask_bp.py ← Move /ask, /ask/async endpoints
  carson_agents/blueprints/orchestrate_bp.py ← Move /orchestrate, /approve, /status
  carson_agents/blueprints/health_bp.py ← Move /health, /refresh-credentials
  carson_agents/blueprints/rag_bp.py ← Move /ingest, /conversations
  (hq_bp.py, guardian_bp.py, actions_bp.py already done)
```

---

## APPENDIX D ADDENDUM: NEW PRIORITY ITEMS (from carson_service.py audit)

### P0.5 — Critical NEW (from carson_service.py deep-read)
21. **Fix docstring: endpoint list says 6, actual is 28+** — Dangerously misleading for any developer reading the file
22. **Remove legacy in-memory `conversation_history`** — Dual context system is redundant; persistent history (max_messages=6) should be sole source

### P1.5 — High Priority NEW
23. **Complete Blueprint migration** — Move /ask, /orchestrate, /health, /ingest endpoints to Flask Blueprints (pattern already established with hq_bp, guardian_bp, actions_bp)
24. **Audit `carson_agents/workflow.py`** — This is where the ACTUAL LangGraph StateGraph lives. Highest-priority unread file.
25. **Audit `carson_agents/orchestrator.py`** — Strands-like supervisor agent. Second-highest-priority unread file.
26. **Fix orchestrator trigger heuristic** — `_is_multi_step_request()` keyword counting is fragile; false-positives for status queries mentioning multiple domains

### P2.5 — Medium Priority NEW
27. **Delete or refactor `fix_chromadb.py`** — `main()` already does backup + health_check + auto-repair with proper config. The standalone script is a worse duplicate.
28. **Clean up Phoenix dead code** — Either fix ASCode issue and re-enable, or remove entirely
29. **Top-level imports** — Eliminate scattered re-imports inside function bodies; use lazy initialization pattern

---

### REMAINING AUDIT BACKLOG (Updated April 13, 2026):
- **`carson_agents/workflow.py`** — **HIGHEST PRIORITY**: Contains actual StateGraph, add_node, add_edge, routing logic
- **`carson_agents/orchestrator.py`** — Strands-like supervisor agent
- `carson_agents/` package (remaining modules) — Agent implementations, RAG module, tools
- `scripts/` folder — Onboarding, ingestion, utilities
- `tests/` folder — Test coverage
- `autonomous_jobs/` — Scheduled tasks
- `requirements.txt` / `pyproject.toml` — Dependencies
- `chroma_db/` contents — Verify vs carson_kb/
- `../mcp-servers/` (19 servers) — Individual MCP implementations

---

## APPENDIX J — ACAMPS Bitbucket Project: Complete Repository Inventory (April 13, 2026)

**Project:** ACAMPS on `bitbucketdc.jpmchase.net`
**Total repos found:** 40+

### J.1 — Core Application Repos

| Repo | Description |
|------|-------------|
| `high-touch-agentic-ai-api` | **MAIN CODEBASE** — FastAPI multi-agent orchestration with AWS Bedrock, LangGraph routing, MCP gateway, RAG. Deploys to ECS Fargate via Jules/JIB |
| `high-touch-agent-prompts` | System prompts, agent instructions, prompt templates for AI/LLM. **ALREADY AUDITED** (see Appendices A-I) |
| `high-touch-mcp-server` | MCP server for the Agentive Platform |
| `high-touch-lambda-confluence-fetcher` | Scheduled Lambda: Confluence pages → S3 → SQS → RAG ingestion (EventBridge) |
| `high-touch-lambdas` | Lambda functions (TBC) |

### J.2 — RAG Pipeline Repos

| Repo | Description |
|------|-------------|
| `high-touch-rag` | RAG pipeline: offline ingestion, chunking, embedding, indexed retrieval |
| `high-touch-rag-ingestion` | Document ingestion: file uploads, chunking, Azure OpenAI embeddings, OpenSearch. SQS consumer for Confluence pages. FastAPI |
| `high-touch-rag-retrieval` | Low-latency vector search on OpenSearch + Azure OpenAI response generation. FastAPI |

### J.3 — AMPS Config Repos (per-product)

| Repo | Product |
|------|---------|
| `high-touch-bond-amps` | Bond |
| `high-touch-credit-data-amps` | Credit Data |
| `high-touch-derivative-amps` | Derivative |
| `high-touch-etf-amps` | ETF |
| `high-touch-exotic-amps` | Exotic |
| `high-touch-insight-amps` | Insight |
| `high-touch-portfolio-amps` | Portfolio |
| `high-touch-sre-amps` | SRE |
| `high-touch-test-amps` | Test workflows |

Each contains CodeDeploy configs + topics.xml for AMPS message routing.

### J.4 — Terraform Infrastructure Repos (15 repos)

| Repo | Purpose | Dependency |
|------|---------|------------|
| `high-touch-terraform-agentic-ai` | **AI System infra**: DynamoDB, S3, SQS, Secrets Manager, IAM for Bedrock | Depends on `fargate` |
| `high-touch-terraform-base` | Private NAT gateway + VPC endpoints for on-prem access | Foundation layer |
| `high-touch-terraform-central` | Core infrastructure of the platform | Depends on `base` |
| `high-touch-terraform-certs` | TLS certificates | Independent |
| `high-touch-terraform-data` | Data layer infrastructure | Foundation layer |
| `high-touch-terraform-datadog` | Datadog Dashboard terraform | Independent (monitoring) |
| `high-touch-terraform-dd` | Datadog Dashboard (variant) | Independent (monitoring) |
| `high-touch-terraform-fargate` | **ECS Fargate** — provisions compute, ALB, SGs, IAM roles | Depends on `central`, `base` |
| `high-touch-terraform-lambdas` | Lambda functions for AMPS cache maintenance | Depends on `central` |
| `high-touch-terraform-lambdas-integration` | Lambda integration (TBC) | TBC |
| `high-touch-terraform-neptune` | Neptune graph database | Depends on `central` |
| `high-touch-terraform-restore-ebs` | EBS snapshot restore via AWS Backup | Independent |
| `high-touch-terraform-route53` | Route53 DNS for Central | Depends on `central` |
| `high-touch-terraform-s3` | S3 for AMPS workflow data storage | Foundation layer |
| `high-touch-terraform-secrets-manager` | AWS Secrets Manager | Independent |

### J.5 — Galvanometer & IDA (Auth) Repos

| Repo | Description |
|------|-------------|
| `high-touch-galvanometer` | Secure frontend using IDA Human-to-App auth |
| `high-touch-galvanometer-route53` | Route53 for Galvanometer Proxy |
| `high-touch-galvanometer-sidecar` | NGINX sidecar for Galvanometer |
| `high-touch-ida` | IDA auth provisioning via IDAnywhere |
| `high-touch-ida-route53` | Route53 for IDA authenticator |
| `high-touch-ida-sidecar` | Health monitor sidecar for IDA Auth Server on ECS |

### J.6 — Other Repos

| Repo | Description |
|------|-------------|
| `high-touch-cicd-orchestrator` | Deployment orchestration across layers (data, s3, central, amps, lambdas) |
| `high-touch-credit-entity-kg` | Credit entity knowledge graph |
| `credit-entity-knowledge-agent` | Knowledge agent for credit entities |
| `gremlin-agent-install` | Gremlin chaos agent on AMPS ASG |
| `gremlin-iam-role` | IAM role for Gremlin (C2C FID mapping) |
| `gremlin-terraform-cert` | KMS key + Gremlin certificate via Terraform |

---

## APPENDIX K — high-touch-terraform-agentic-ai: Full Audit (April 13, 2026)

**Repo:** `ACAMPS/high-touch-terraform-agentic-ai` (branch: develop)
**Description:** "Agentic AI System Infrastructure - Smart SDK Integration with Bedrock"
**Author:** Garcia Tejeda, Martin — last commit 9d796c4062c (26 Mar 2026)
**Jira ticket:** CREDITTECH-241864

### K.1 — File Structure

```
high-touch-terraform-agentic-ai/
├── environments/              # Environment-specific configs
├── variables/                 # Variable definition files
├── .gitignore                 # 5.25 KB
├── BEDROCK_CONFIG.md          # 10.04 KB — Bedrock + Spinnaker pipeline config docs
├── Jenkinsfile                # 160 B — Standard Jules pattern
├── jib.yml                    # 14.64 KB — Build config with changeRecordNumber + productionDeployment flag
├── jules.yml                  # 161 B — Jules CI config
├── locals.tf                  # 2.28 KB — Local values (name_prefix, common_tags, tfe_org)
├── main.tf                    # 13.49 KB — Core terraform: all resources
├── outputs.tf                 # 6.04 KB — Output definitions
├── README.md                  # 11.01 KB — Renamed from "Jarvis" to "Carson"
├── spinnaker-trigger.yml      # 565 B — Spinnaker deployment trigger
└── variables.tf               # 5.06 KB — Input variables
```

### K.2 — Provider & Backend Configuration

- **Terraform:** `>=1.3.6`
- **Provider:** `atlas` from `jpmchase.net/terraform/atlas-aws` (JPMC internal)
- **AWS Provider:** access_key/secret_key/token vars, `sts_region = "us-east-1"`
- **Assume Role:** `arn:aws:iam::${var.aws_account_id}:role/tfe-module-pave-apply`
- **Default Tags:** `local.common_tags`
- **Module:** `jpm-data` from `tfe.jpmchase.net/ATLAS-MODULE-REGISTRY/jpm-data/aws` v9.9.0

### K.3 — Remote State Dependency

```hcl
data "terraform_remote_state" "fargate" {
  backend = "remote"
  config = {
    organization = local.tfe_org
    workspaces = { name = "ht-fargate" }
  }
}
```

**Reuses from fargate:** VPC, subnets, ECS Cluster, ALB, Security Groups, IAM roles for ECS tasks.

### K.4 — Resources Created (All Use ATLAS-MODULE-REGISTRY)

**S3 — Knowledge Base Data:**
- Module: `s3_kdb_data` (ATLAS s3/aws v12.6.0)
- Bucket: `${local.name_prefix}-kdb-data`
- Lifecycle: transition to STANDARD_IA at 90 days, expiration at 180 days
- Versioning: disabled

**Secrets Manager:**
- Module: `secrets_manager` (ATLAS secrets-manager/aws v10.2.0)
- Name: `${local.name_prefix}-app-secrets`
- Secrets stored: `ANTHROPIC_API_KEY`, `BRAVE_API_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`
- Recovery window: 7 days
- **⚠ FINDING: rotation_enabled = false** — Should enable secret rotation for production security

**DynamoDB Tables (4 tables, all ATLAS dynamodb/aws v11.0.0):**

| Table | Hash Key | Range Key | TTL | Notes |
|-------|----------|-----------|-----|-------|
| `{prefix}-agent-registry` | agent_id (S) | — | No | Agent configuration storage |
| `{prefix}-sessions` | session_id (S) | timestamp (N) | expiration_time | Conversation session tracking |
| `{prefix}-mcp-registry` | tool_name (S) | — | No | MCP tool/server registry |
| `{prefix}-token-usage` | request_id (S) | timestamp (N) | expiration_time | LLM token usage tracking |

All tables: PAY_PER_REQUEST billing, SSE enabled, PITR enabled in prod only.

**SQS:**
- Module: `sqs_async_tasks` (ATLAS sqs/aws v18.1.2)
- Queue: `${local.name_prefix}-async-tasks`
- Visibility timeout: 300s, retention: 14 days, long polling: 20s
- Dead Letter Queue: enabled

**IAM Policies (5, all attached to fargate ECS task role):**
1. **Bedrock access** — invoke model permissions
2. **DynamoDB access** — CRUD on all 4 tables
3. **S3 access** — GetObject, PutObject, DeleteObject, ListBucket on kdb-data bucket
4. **Secrets Manager access** — GetSecretValue, DescribeSecret
5. **SQS access** — SendMessage, ReceiveMessage, DeleteMessage, GetQueueAttributes

### K.5 — Audit Findings

1. **WELL-STRUCTURED** — Clean separation, proper use of TFE modules, remote state, tags, lifecycle rules
2. **CRITICAL DEPENDENCY:** `high-touch-terraform-fargate` (workspace: "ht-fargate") is the ONLY upstream terraform dependency — must be deployed first
3. **⚠ SECRET ROTATION DISABLED** — `rotation_enabled = false` on Secrets Manager. For ANTHROPIC_API_KEY and LANGFUSE keys in production, enable rotation or document the exception
4. **⚠ SINGLE REGION** — No multi-region support. The AMPS modularization strategy (Appendix in memory) calls for NA (us-east-1), EMEA (eu-west-2), APAC (ap-southeast-1). This repo only targets one region
5. **S3 VERSIONING DISABLED** — `versioning_enabled = false` on kdb-data bucket. Consider enabling for knowledge base data integrity
6. **GOOD: TTL on sessions and token-usage** — Auto-cleanup prevents unbounded table growth
7. **GOOD: DLQ on SQS** — Failed async tasks are captured for retry/debugging
8. **GOOD: PAY_PER_REQUEST billing** — Cost-efficient for variable workloads
9. **RENAME ARTIFACT:** README was updated from "Jarvis" to "Carson" (commit 20 Mar 2026) — verify no other Jarvis references remain

### K.6 — Terraform Deployment Order (Cross-Repo Dependencies)

Based on ACAMPS inventory and remote state analysis:

```
LAYER 1 (Foundation — no dependencies):
  ├── high-touch-terraform-data
  ├── high-touch-terraform-s3
  ├── high-touch-terraform-certs
  ├── high-touch-terraform-secrets-manager
  └── high-touch-terraform-base (VPC, NAT, endpoints)

LAYER 2 (Core — depends on Layer 1):
  └── high-touch-terraform-central (depends on base)

LAYER 3 (Compute & Network — depends on Layer 2):
  ├── high-touch-terraform-fargate (depends on central, base)
  ├── high-touch-terraform-lambdas (depends on central)
  ├── high-touch-terraform-neptune (depends on central)
  └── high-touch-terraform-route53 (depends on central)

LAYER 4 (Application — depends on Layer 3):
  └── high-touch-terraform-agentic-ai (depends on fargate via remote state)

INDEPENDENT (deploy anytime):
  ├── high-touch-terraform-datadog
  ├── high-touch-terraform-dd
  └── high-touch-terraform-restore-ebs

AMPS CONFIG DEPLOYMENT (after Layer 3):
  high-touch-cicd-orchestrator orchestrates: data → s3 → base → central → amps-configs → lambdas
```

**Critical path:** `base` → `central` → `fargate` → `agentic-ai`

---

## APPENDIX L — high-touch-terraform-fargate: Full Audit (April 14, 2026)

**Repo:** `ACAMPS/high-touch-terraform-fargate` (branch: main)
**Description:** "Repository to provision and manage ECS Fargate resources of the High Touch AWS Platform"
**Author:** Garcia Tejeda, Martin — last commit c1951ff481e (07 Aug 2025)
**Jira ticket:** CREDITTECH-223186

### L.1 — File Structure

```
high-touch-terraform-fargate/
├── variables/              # Variable definition files
├── .gitignore             # 1000 B
├── .terraformignore       # 21 B
├── alb.tf                 # 13.28 KB — ALB, NLB, security groups, listeners (LARGEST FILE)
├── data.tf                # 2.74 KB — Data sources: CloudFormation exports, SSM params, subnets
├── iam.tf                 # 527 B — IAM policy updater
├── Jenkinsfile            # 158 B — Standard Jules pattern
├── jib.yml                # 43.55 KB — Very large build config (multi-env deployments)
├── jules.yml              # 160 B — Jules CI config
├── locals.tf              # 1.79 KB — Local values
├── main.tf                # 877 B — ECS cluster + jpm_data modules only
├── outputs.tf             # 1.41 KB — 8 outputs consumed by agentic-ai via remote state
├── providers.tf           # 1.37 KB
├── security_groups.tf     # 160 B
├── spinnaker-trigger.yml  # 561 B — Spinnaker deployment trigger
└── variables.tf           # 2.28 KB — Input variables
```

### L.2 — Modules Used (main.tf)

1. **`jpm_data`** — `tfe.jpmchase.net/ATLAS-MODULE-REGISTRY/jpm-data/aws` v9.9.0 (same as agentic-ai)
2. **`ecs_cluster`** — `tfe.jpmchase.net/ATLAS-MODULE-REGISTRY/ecs-cluster/aws` v2.49.0
   - Cluster name pattern: `ht-fargate-${region}[-${qualifier}]`
   - Source registry: `jetse-publish.prod.aws.jpmchase.net`
   - Capacity providers: **FARGATE_SPOT** (base=1, weight=1) + **FARGATE** (base=null, weight=1)
   - ECR: enabled, Datadog: enabled, Datadog logging: enabled, X-Ray: disabled
   - Gateway: disabled (no API Gateway integration)

### L.3 — Data Sources & Upstream Dependencies (data.tf) — CRITICAL FINDING

**⚠ CORRECTED DEPENDENCY MODEL:** Fargate does NOT use `terraform_remote_state` to depend on central or base. Instead it uses:

1. **CloudFormation Exports** (from JPMC core stacks, not terraform):
   - `core-Vpc01-Id` → VPC ID
   - `core-ELBAccessLogsBucket-Name` → ALB access logs S3 bucket

2. **SSM Parameters** (account metadata):
   - `/account/classification` — Account classification
   - `/core/account/sealappid` — SEAL app ID
   - `/services/account/cloudprovider` — Cloud provider
   - `/core/account/sealappdeploymentid` — SEAL deployment ID
   - `/core/account/environment` — Environment name

3. **AWS Data Sources** (dynamic discovery):
   - `aws_subnets` "private_subnet_list" — filtered by `tag:Name = "Private*"`
   - `aws_subnet` ALB subnets — by tag name
   - `aws_security_group` "EdgeSecurityGroup" — for on-prem access
   - `aws_vpc_endpoint` monitoring — CloudWatch VPC endpoint

4. **Atlas Blueprint**: `data "atlas_blueprint" "main" {}` — JPMC metadata and tags

**IMPLICATION:** The terraform deployment layer model in K.6 needs correction. Fargate depends on **JPMC core CloudFormation stacks** (VPC, S3, SGs), NOT on `terraform-base` or `terraform-central` repos via remote state. The actual dependency chain is:

```
JPMC Core CloudFormation Stacks (VPC, subnets, SGs, S3 buckets)
  └── high-touch-terraform-fargate (reads via CF exports + SSM + data sources)
        └── high-touch-terraform-agentic-ai (reads via terraform_remote_state "ht-fargate")
```

### L.4 — ALB & NLB Configuration (alb.tf — 13.28 KB)

**Security Group (`alb_sg`):**
- VPC ID from CloudFormation export
- Ingress: ports 443 + 19158 (AMPS protocol) from VPC CIDRs, JPMC Public Cloud, Desktop LVDI, Athena UAT
- Egress: ports 443 + 19158 to VPC CIDRs and 0.0.0.0/0
- Additional: CloudWatch monitoring VPC endpoint egress on 443

**Application Load Balancer (`aws_lb "alb"`):**
- **Internal = true** — private, not internet-facing
- Subnets: ALB subnets by tag
- Security groups: `alb_sg` + EdgeSecurityGroup (for on-prem)
- Access logs: enabled, bucket from CF export
- Idle timeout: 300s
- Tags: `ECS_CLUSTER = "high-touch-fargate"`

**ALB Listener (`alb_listener`):**
- Port 443, HTTPS
- Certificate: ACM cert (`data.aws_acm_certificate.app_cert.arn`)
- SSL Policy: `ELBSecurityPolicy-TLS13-1-3-2021-06` — **TLS 1.3 only (good security)**
- Default action: fixed-response 404 "ALB Default Response" (safe default)

**NLB Module (`module "nlb"`):**
- Source: `tfe.jpmchase.net/ATLAS-MODULE-REGISTRY/nlb/aws` v16.0.0
- Certificate: same ACM cert
- **on_prem_accessible = true** — reachable from JPMC on-prem network
- VPC subnets: public subnets by tag name

**Galvanometer (auth frontend) — separate ALB + NLB:**
- `aws_lb "alb-galvanometer"` — separate ALB for Galvanometer auth proxy
- `module "nlb-galvanometer"` — separate NLB
- `alb-galvanometer_listener` — separate listener
- Uses different certificate: `data.aws_acm_certificate.galvanometer_cert.arn`

### L.5 — Outputs Consumed by Downstream (outputs.tf)

| Output | Description | Value Source | Consumer |
|--------|------------|-------------|----------|
| `aws_region` | ECS Cluster region | `var.aws_region` | agentic-ai |
| `ecs_cluster_details` | Full ECS cluster module | `module.ecs_cluster` | agentic-ai |
| `nlb` | NLB module | `module.nlb` | agentic-ai |
| `alb` | ALB resource | `aws_lb.alb` | agentic-ai |
| `alb_listener` | ALB HTTPS listener | `aws_lb_listener.alb_listener` | agentic-ai |
| `nlb-galvanometer` | Galvanometer NLB | `module.nlb-galvanometer` | galvanometer repos |
| `alb-galvanometer` | Galvanometer ALB | `aws_lb.alb-galvanometer` | galvanometer repos |
| `alb-galvanometer_listener` | Galvanometer listener | `aws_lb_listener...` | galvanometer repos |

### L.6 — Audit Findings

1. **WELL-STRUCTURED** — Clean split into domain-specific .tf files (alb.tf, data.tf, iam.tf, main.tf)
2. **⚠ CORRECTED DEPENDENCY MAP** — Fargate depends on JPMC CloudFormation stacks, NOT terraform-base/central via remote state. Only `agentic-ai` uses `terraform_remote_state`
3. **GOOD: TLS 1.3 only** — `ELBSecurityPolicy-TLS13-1-3-2021-06` enforces modern TLS
4. **GOOD: Internal ALB** — Not internet-facing, accessible only from VPC + on-prem
5. **GOOD: FARGATE_SPOT + FARGATE** — Cost optimization with spot instances, on-demand as fallback
6. **GOOD: Safe default action** — 404 fixed-response for unmatched ALB requests
7. **GOOD: Access logging enabled** — ALB logs to S3 for audit trail
8. **⚠ DELETION PROTECTION DISABLED** — `enable_deletion_protection = false` on ALB. Consider enabling in production
9. **⚠ jib.yml = 43.55 KB** — Unusually large build config suggests complex multi-environment deployment matrix
10. **DUAL LOAD BALANCER ARCHITECTURE** — Separate ALB+NLB for main services AND Galvanometer auth — good isolation of auth traffic
11. **PORT 19158** — AMPS-specific protocol port open alongside 443 for AMPS messaging

### L.7 — Corrected Terraform Deployment Order (Verified)

```
LAYER 0 (JPMC Core — CloudFormation, not terraform):
  ├── core VPC stack (exports core-Vpc01-Id)
  ├── core S3 stack (exports core-ELBAccessLogsBucket-Name)
  ├── SSM parameters (/account/*, /core/account/*, /services/account/*)
  └── Edge Security Groups, ACM certificates

LAYER 1 (Foundation terraform — no terraform cross-dependencies):
  ├── high-touch-terraform-data
  ├── high-touch-terraform-s3
  ├── high-touch-terraform-certs
  ├── high-touch-terraform-secrets-manager
  ├── high-touch-terraform-base (Private NAT + VPC endpoints)
  └── high-touch-terraform-fargate (depends on LAYER 0 CloudFormation, NOT other terraform repos)

LAYER 2 (Core terraform — may depend on Layer 1):
  ├── high-touch-terraform-central (depends on base)
  ├── high-touch-terraform-lambdas (depends on central)
  ├── high-touch-terraform-neptune (depends on central)
  └── high-touch-terraform-route53 (depends on central)

LAYER 3 (Application terraform — depends on fargate via remote state):
  └── high-touch-terraform-agentic-ai (depends on fargate workspace "ht-fargate")

INDEPENDENT (deploy anytime):
  ├── high-touch-terraform-datadog
  ├── high-touch-terraform-dd
  └── high-touch-terraform-restore-ebs

AMPS CONFIG DEPLOYMENT (orchestrated by cicd-orchestrator):
  data → s3 → base → central → amps-configs → lambdas
```

**Key correction from K.6:** Fargate is in LAYER 1, not LAYER 3. It depends on CloudFormation, not on central/base terraform. Only `agentic-ai` has a `terraform_remote_state` cross-repo dependency.

**Verified critical path for Carson AI infrastructure:**
`JPMC Core CF` → `fargate` → `agentic-ai`

---

---

> ⚠️ **APÉNDICES M–R SON DE OTRO REPO**: `high-touch-agentic-ai-api` (no es `high-touch-agent-prompts`). Mantenidos como referencia del ecosistema Carson pero NO son fuente para mejoras del repo objetivo.

## Appendix M — LangGraph Architecture Audit (high-touch-agentic-ai-api)

**Source:** `bitbucketdc.jpmchase.net/projects/ACAMPS/repos/high-touch-agentic-ai-api`
**Branch:** `feature/CREDITTECH-241864-initial-scaffold`
**Audited files:** `src/graph/state.py` (1.05 KB, 37 lines), `src/graph/workflow.py` (2.57 KB, ~79 lines), `src/graph/nodes.py` (4.88 KB, ~124 lines)
**Committed:** 26 Mar 2026 by Garcia Tejeda, Martin (commit `08e15a2f146`)

### M.1 — State Schema (state.py)

`AgentState(TypedDict)` — shared state passed between all LangGraph nodes:

| Field | Type | Set by | Purpose |
|---|---|---|---|
| `query` | `str` | intake_node | User input (stripped) |
| `rag_context` | `Optional[List[dict]]` | retrieve_node | `[{"text": ..., "source": ..., "distance": ...}]` |
| `research` | `Optional[str]` | strands_node | Raw research from Strands agents |
| `synthesis` | `Optional[str]` | strands_node | Synthesized response text |
| `routing_plan` | `Optional[dict]` | strands_node | Serialized RouterDecision for Langfuse: `{"agents": [...], "strategy": ..., "reasoning": ...}` |
| `confidence` | `Optional[str]` | strands_node | `"HIGH"` / `"MEDIUM"` / `"LOW"` |
| `final_response` | `Optional[str]` | format_node | User-facing assembled output |
| `error` | `Optional[str]` | any node | Error propagation (checked by every subsequent node) |

**Design notes:** Clean separation of concerns. Each node writes only its designated fields. The `routing_plan` and `confidence` fields are for observability/tracing (Langfuse), not for graph routing — the graph itself is fully linear.

### M.2 — Graph Topology (workflow.py)

**Topology:** `START → intake → retrieve → strands → format → END`

This is a **strictly linear chain** — no `add_conditional_edges`, no branching, no parallel paths. The code explicitly labels this: `# — Edges (linear for POC)`.

```
build_graph() → StateGraph:
    graph = StateGraph(AgentState)
    # 4 nodes
    graph.add_node("intake", intake_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("strands", strands_node)       # ← Strands multi-agent group
    graph.add_node("format", format_node)
    # 5 edges (linear)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "retrieve")
    graph.add_edge("retrieve", "strands")
    graph.add_edge("strands", "format")
    graph.add_edge("format", END)
    return graph.compile()
```

**Singleton pattern:** `get_graph()` lazily builds and caches the compiled graph in a module-level `_compiled_graph` variable. Thread-safe at the GIL level for CPython.

**`run_query(query: str) -> dict`** — convenience wrapper:
- Initializes full `AgentState` with all fields set to `None` (except `query`)
- **BUG FOUND:** `routing_plan` and `confidence` are NOT initialized in `run_query`'s `initial_state` dict, but they ARE in `AgentState`. TypedDict doesn't enforce runtime, but this inconsistency should be fixed.
- Attaches Langfuse callback handler if observability is enabled
- Uses `config.GRAPH_RECURSION_LIMIT` from config

### M.3 — Node Implementations (nodes.py)

**Node 1: `intake_node`** (L26-34) — Validation only
- Strips whitespace from query
- Returns `{"error": ..., "final_response": ...}` on empty query
- Otherwise returns `{"query": query, "error": None}`

**Node 2: `retrieve_node`** (L39-60) — Conditional RAG retrieval
- **Early exit:** Returns `{}` if `state.get("error")` — error propagation
- **Financial query bypass:** Imports `_is_financial_query` from `src.agents.orchestrator`. If financial → returns `{"rag_context": []}` (empty). Comment explains: specialist agents (esp. amps-agent) do their own `search_knowledge_base` calls, so in-process retrieval is skipped to avoid loading SentenceTransformer twice and spiking memory.
- **Non-financial path:** `get_retriever()` → `retriever.retrieve(query)` → returns `{"rag_context": docs}`
- **Error handling:** Generic except returns `{"error": ..., "rag_context": []}`

**Node 3: `strands_node`** (L65-103) — Multi-agent orchestration
- **Key insight:** This single LangGraph node INTERNALLY runs Researcher + Synthesizer agents sequentially via `run_strands_orchestrator`. LangGraph sees it as one node, but the actual multi-agent logic is inside `src.agents.orchestrator`.
- **Retry logic:** 3 retries with exponential backoff (5s → 10s → 20s) for transient Anthropic/LiteLLM errors (overloaded, serviceunavailable, rate_limit, 529, too many requests)
- **Input:** `query` + `rag_context`
- **Output:** `research`, `synthesis`, `routing_plan`, `confidence` (all from orchestrator result object)
- **Error handling:** Retryable errors → sleep + retry. Non-retryable → immediate return with traceback. All retries exhausted → return with full traceback.

**Node 4: `format_node`** (L108-124) — Response assembly
- If error in state → returns `{"final_response": f"Error: {state['error']}"}`
- Extracts unique sources from `rag_context` (sorted, deduplicated)
- Appends sources block: `\n\n---\n**Sources:** src1 | src2 | src3`
- Returns `{"final_response": synthesis + sources_block}`

### M.4 — Critical Audit Findings

**FINDING M-1 (Architecture — Linear Graph is POC-appropriate but limits production use):**
The graph is purely linear with no conditional routing. Every query — whether a simple greeting, a financial question, or a terraform lookup — follows the exact same 4-node pipeline. This means:
- RAG retrieval runs on EVERY non-financial query even if the strands orchestrator won't use it
- No short-circuit for queries that don't need agent orchestration
- No parallel execution of independent nodes
- **Recommendation:** Add `add_conditional_edges` from `intake` based on query classification. Route simple queries directly to format, financial queries to a dedicated path, and complex queries through full RAG+strands pipeline.

**FINDING M-2 (Bug — Missing state keys in run_query initial_state):**
`run_query` initializes `initial_state` with `query`, `rag_context`, `research`, `synthesis`, `final_response`, `error` — but omits `routing_plan` and `confidence` which are defined in `AgentState`. While `TypedDict` doesn't enforce at runtime (Python dicts accept missing keys), this creates an inconsistency that could cause `KeyError` if any code does `state["routing_plan"]` instead of `state.get("routing_plan")`.
- **Fix:** Add `"routing_plan": None, "confidence": None` to `initial_state` in `run_query`.

**FINDING M-3 (Design — Multi-agent logic hidden inside single node):**
The entire Researcher + Synthesizer agent orchestration is collapsed into a single LangGraph node (`strands`). This means:
- Langfuse graph tracing shows 4 nodes, not the actual agent execution tree
- If the researcher succeeds but synthesizer fails, the ENTIRE node retries from scratch
- No ability to checkpoint between research and synthesis phases
- **Recommendation for v2:** Split into `strands_research` and `strands_synthesis` nodes, or use LangGraph subgraphs for the orchestrator.

**FINDING M-4 (Error propagation — Silent pass-through, no recovery):**
Error propagation uses a simple `if state.get("error"): return {}` pattern in every node after intake. Once an error is set, all subsequent nodes are skipped and `format_node` wraps the error message. This means:
- No retry at the graph level for retrieve_node failures
- Only strands_node has retry logic (for Anthropic overload errors)
- retrieve_node failures permanently poison the pipeline with no recovery
- **Recommendation:** Add a graph-level error handler node or use conditional edges to route error states to a recovery/fallback path.

**FINDING M-5 (Performance — Blocking sleep in retry loop):**
`strands_node` uses `time.sleep(delay)` for retry backoff (5s, 10s, 20s). In a FastAPI async service, this blocks the event loop thread for up to 35 seconds total (worst case all 3 retries). This will degrade throughput under load.
- **Fix:** Use `asyncio.sleep()` and make `strands_node` async, or offload to a thread pool.

**FINDING M-6 (Good — Singleton compilation pattern):**
The `get_graph()` → `_compiled_graph` singleton pattern avoids recompiling the StateGraph on every request. This is correct and performant.

**FINDING M-7 (Good — Retry logic for Anthropic rate limits):**
The exponential backoff retry in `strands_node` (5s → 10s → 20s) with string-matching for known transient errors is a pragmatic approach for Bedrock/Anthropic overload scenarios. The retryable phrases tuple covers the common error patterns.

### M.5 — Relationship to Prompts Repo (high-touch-agent-prompts)

The `src/graph/` in `high-touch-agentic-ai-api` is the **runtime implementation**. The `high-touch-agent-prompts` repo (audited in Appendices A-I) contains the **prompt templates and agent instructions**. The connection:
- `src/agents/orchestrator.py` (imported by `strands_node`) calls the LLM with prompts loaded from the prompts repo
- `src/rag/retriever.py` (imported by `retrieve_node`) uses ChromaDB with embeddings built from knowledge bases defined in the prompts repo
- The `routing_plan` field in `AgentState` corresponds to the `RouterDecision` concept seen in the prompts repo's router templates

### M.6 — Files Still Requiring Audit in high-touch-agentic-ai-api

| File/Folder | Size | Priority | Why |
|---|---|---|---|
| `src/agents/orchestrator.py` | unknown | **CRITICAL** | Contains `run_strands_orchestrator`, `_is_financial_query` — the actual multi-agent brain |
| `src/agents/` (other files) | unknown | HIGH | Individual agent implementations |
| `src/config.py` | 8.37 KB | HIGH | `GRAPH_RECURSION_LIMIT` and all runtime config |
| `src/rag/retriever.py` | unknown | HIGH | `get_retriever()` — ChromaDB/embedding model setup |
| `src/mcp_clients.py` | 9.08 KB | MEDIUM | MCP gateway client setup |
| `src/observability.py` | 7.78 KB | MEDIUM | `get_langfuse_callback()` — Langfuse integration |
| `src/api/` | unknown | MEDIUM | FastAPI router definitions |
| `src/services/` | unknown | MEDIUM | Business logic services |
| `src/a2a/` | unknown | LOW | Agent-to-agent protocol |
| `src/mcp_gateway/` | unknown | LOW | MCP gateway server |

---

### REMAINING AUDIT BACKLOG (Updated April 14, 2026):
- ~~**`src/agents/orchestrator.py`**~~ — COMPLETED (see Appendix N)
- **`src/agents/llm_router.py`** (10.65 KB) — **HIGH PRIORITY**: LLM Router for financial query classification (Phase 3 entry)
- ~~**`src/agents/financial_orchestrator.py`** (6.35 KB) — Phase 1 in-process financial orchestrator~~ ✅ **COMPLETED → Appendix Q**
- ~~**`src/agents/financial_orchestrator_v2.py`** (6.38 KB) — Phase 2 variant~~ ✅ **COMPLETED → Appendix Q**
- **`src/agents/`** (other files) — Domain specialist agents (amps, cds, etf, kdb, portfolio, risk_pnl)
- **`src/a2a/parallel_client.py`** — A2A parallel agent caller (AgentResult dataclass, call_agents_parallel_sync)
- ~~**`src/a2a/client.py`** — A2A single agent caller (call_agent_sync)~~ ✅ **COMPLETED → Appendix Q**
- ~~**`src/a2a/registry.py`** — Agent registry (get_endpoint)~~ ✅ **COMPLETED → Appendix Q**
- **`src/config.py`** (8.37 KB) — Runtime config including `GRAPH_RECURSION_LIMIT`
- **`src/rag/retriever.py`** — ChromaDB retriever, `get_retriever()` factory
- **`src/mcp_clients.py`** (9.08 KB) — MCP gateway client, `open_mcp_tools()`
- **`src/observability.py`** (7.78 KB) — Langfuse integration
- **`src/api/`**, **`src/services/`**, **`src/mcp_gateway/`** — Remaining source directories
- `scripts/` folder — Onboarding, ingestion, utilities
- `tests/` folder — Test coverage
- `autonomous_jobs/` — Scheduled tasks
- `requirements.txt` / `pyproject.toml` — Dependencies
- `chroma_db/` contents — Verify vs carson_kb/
- `../mcp-servers/` (19 servers) — Individual MCP implementations
- **`high-touch-terraform-agentic-ai` — environments/ and variables/ folders** (not yet read)
- **`BEDROCK_CONFIG.md`** (10.04 KB) — Bedrock integration details not yet read
- **Remaining terraform repos** — terraform-central, terraform-base, terraform-lambdas deep-reads (13 repos remain)
- **high-touch-terraform-fargate — iam.tf, locals.tf, providers.tf, security_groups.tf** (small files not yet read)

---

## Appendix N — Orchestrator Architecture Audit (`src/agents/orchestrator.py`)

**File**: `src/agents/orchestrator.py` (10 KB, 257 lines)
**Branch**: `feature/CREDITTECH-241864-initial-scaffold`
**Audit date**: April 14, 2026

### N.1 Module Overview

The orchestrator is the **multi-agent brain** — the single function that LangGraph's `strands_node` calls. It routes queries to either financial domain specialists or the general Researcher+Synthesizer pipeline.

**Entry point**: `run_strands_orchestrator(query, rag_context) -> OrchestratorResult`

### N.2 Query Routing — `_is_financial_query()`

```
_FINANCIAL_KEYWORDS = {"bond", "rfq", "trader", "trading", "desk", "spread", "bps",
    "yield", "coupon", "isin", "cusip", "live", "real-time", "current price",
    "market data", "bid", "ask", "pnl", "mtm", "amps", "sow", "subscribe",
    "pub/sub", "topic", "kdb", "historical", "history", ...}  # ~50+ keywords

def _is_financial_query(query: str) -> bool:
    return any(kw in query.lower() for kw in _FINANCIAL_KEYWORDS)
```

**Routing logic**: Keyword substring match on lowercased query. No LLM call for the initial branch decision (low latency).

### N.3 Financial Pipeline — Three-Phase Fallback Architecture

`_run_financial()` implements a cascading 3-phase strategy controlled by environment variables:

**Phase 3 (default)** — `AGENT_SERVICE == "api"`:
- Imports `route_query` from `src.agents.llm_router` (LLM-based classification)
- Imports `call_agents_parallel_sync` from `src.a2a.parallel_client`
- `decision = route_query(query)` → returns agents list with id/priority/timeout_ms, strategy, reasoning, fallback_used
- Builds `routing_plan` dict for Langfuse tracing
- If `decision.strategy == "sequential"`: loops agents one-by-one via `call_agents_parallel_sync([agent_config], full_query)`
- If parallel: single call `call_agents_parallel_sync(decision.agents, full_query)`
- Computes confidence via `_compute_confidence(results)`
- Single-agent result → uses directly; multi-agent → merges via `_merge_parallel_results()`
- **FINDING N-1**: `synthesis=research_text` — Phase 3 skips synthesis, copying research as-is

**Phase 2 fallback** — `FINANCIAL_ORCHESTRATOR_URL` is set:
- Single A2A HTTP call to external financial-orchestrator service
- `endpoint = get_endpoint("financial-orchestrator", fin_url)`
- `research_text = call_agent_sync(endpoint, full_query)`
- **FINDING N-2**: Also skips synthesis (`synthesis=research_text`)

**Phase 1 fallback** — No env vars set (in-process):
- Imports `run_financial_orchestrator` from `src.agents.financial_orchestrator`
- Runs in-process financial orchestrator
- **Does** create a separate `create_synthesizer()` and runs synthesis
- The ONLY financial phase with actual synthesis step

### N.4 General Pipeline — `_run_general()`

```
Researcher (with MCP tools) → research_text → Synthesizer → synthesis_text
```

- Builds `research_prompt` from query + optional RAG pre-context block
- **MCP tool integration**: `open_mcp_tools(docs_path=config.MCP_FILESYSTEM_PATH)` provides filesystem access to the researcher
- **MCP fallback**: If MCP tools unavailable, creates researcher with `extra_tools=[]` and logs warning
- `create_researcher(extra_tools=mcp_tools)` → `researcher(research_prompt)` → `str(response)`
- `create_synthesizer()` → `synthesizer(synthesis_prompt)` → `str(response)`
- Synthesis prompt: "Original question: {query}\n\nResearch findings:\n{research_text}\n\nPlease synthesize a clear, structured answer."
- Returns `OrchestratorResult(research=research_text, synthesis=synthesis_text, route="general")`

### N.5 Helper Functions

**`_compute_confidence(results: dict) -> str`**:
- Imports `AgentResult` from `src.a2a.parallel_client`
- Checks `r.success` and `r.priority` ("required" vs "optional") across all results
- `required_failed` → "LOW"; `optional_failed` → "MEDIUM"; else → "HIGH"
- Clean, well-documented logic

**`_merge_parallel_results(query, results, confidence) -> str`**:
- Builds markdown sections per agent: `## Agent Name\n\n{result.text}`
- Handles timed_out → `[TIMED OUT — data unavailable]`, error → `[ERROR — {error}]`, success → content
- Tracks `gaps` list for missing data
- Joins sections with `\n\n---\n\n` separators
- Footer: `**Data confidence: {confidence}**` + missing data from gaps
- Returns formatted markdown: `# Multi-Source Financial Analysis\n\nQuery: {query}\n\n{merged}{footer}`

### N.6 OrchestratorResult Dataclass

```python
@dataclass
class OrchestratorResult:
    research: str
    synthesis: str
    route: str = "general"           # "general" | "financial"
    confidence: str = "HIGH"         # "HIGH" | "MEDIUM" | "LOW"
    routing_plan: dict | None = field(default=None, repr=False)  # for Langfuse tracing
```

### N.7 Key Dependencies Map

| Import | Source | Used By |
|--------|--------|---------|
| `create_researcher` | `src.agents.researcher` | `_run_general` |
| `create_synthesizer` | `src.agents.synthesizer` | `_run_general`, `_run_financial` (Phase 1 only) |
| `config` | `src.config` | `_run_general` (MCP_FILESYSTEM_PATH) |
| `open_mcp_tools` | `src.mcp_clients` | `_run_general` |
| `route_query` | `src.agents.llm_router` | `_run_financial` (Phase 3) |
| `call_agents_parallel_sync` | `src.a2a.parallel_client` | `_run_financial` (Phase 3) |
| `call_agent_sync` | `src.a2a.client` | `_run_financial` (Phase 2) |
| `get_endpoint` | `src.a2a.registry` | `_run_financial` (Phase 2) |
| `run_financial_orchestrator` | `src.agents.financial_orchestrator` | `_run_financial` (Phase 1) |
| `AgentResult` | `src.a2a.parallel_client` | `_compute_confidence`, `_merge_parallel_results` |

### N.8 Audit Findings

**Finding N-1 (DESIGN — Medium)**: Financial Phase 3 and Phase 2 skip synthesis step.
- `synthesis=research_text` — the synthesis field is just a copy of research
- Only Phase 1 (in-process fallback) runs actual synthesis
- **Impact**: When Phase 3 (the default production path) is active, financial answers lack the synthesis refinement that general queries get
- **Action**: Either add synthesis step to Phase 3/2, or document this as intentional (specialist agents may produce synthesis-quality output natively)

**Finding N-2 (DESIGN — Medium)**: RAG context assembly duplicated across three functions.
- `_run_financial` (lines 90-96) and `_run_general` (lines 223-230) both build numbered snippet blocks from `rag_context`
- Identical pattern: `f"[{i+1}] {doc['text']}"` joined by `\n\n`
- **Action**: Extract to shared `_format_rag_context(rag_context)` helper

**Finding N-3 (DESIGN — Low)**: Keyword routing has false-positive risk.
- `_is_financial_query` uses substring matching: `any(kw in query.lower() for kw in _FINANCIAL_KEYWORDS)`
- "history" matches financial → a query like "What is the history of our deployment pipeline?" routes to financial
- "live" matches financial → "How do I access the live documentation?" routes to financial
- **Action**: Consider multi-word keywords only, or add a confidence threshold using the LLM Router as primary classifier

**Finding N-4 (DESIGN — Low)**: `import os` inside function body (line 88).
- `_run_financial` imports `os` at runtime instead of module top level
- This is a minor style issue but consistent with lazy-import pattern used for other modules
- **Action**: Move to top-level imports for clarity

**Finding N-5 (ARCHITECTURE — High)**: Phase 3 `call_agents_parallel_sync` is synchronous blocking.
- Despite the name "parallel_sync", the sequential strategy loops agents and blocks on each one
- Combined with `strands_node` retry loop (5s→10s→20s), a failing Phase 3 financial query could block for 35+ seconds per retry × 3 retries = 105 seconds total
- **Action**: Add circuit breaker or total timeout to `_run_financial` to cap worst-case latency

**Finding N-6 (ARCHITECTURE — Medium)**: No error handling in `_run_financial` body.
- If `route_query(query)` raises, or `call_agents_parallel_sync` raises an unhandled exception, the entire function crashes
- `strands_node` retry catches some errors, but unhandled exceptions propagate to LangGraph
- **Action**: Wrap Phase 3 body in try/except with fallback to Phase 2/Phase 1

**Finding N-7 (GOOD PATTERN)**: Three-phase fallback design is resilient.
- Environment-variable-controlled phase selection allows gradual rollout
- Phase 3 (distributed A2A) → Phase 2 (single A2A) → Phase 1 (in-process) is a sound degradation strategy
- `routing_plan` dict captured for Langfuse observability is excellent

**Finding N-8 (GOOD PATTERN)**: MCP tools graceful degradation in `_run_general`.
- `try/except` around MCP tool initialization with fallback to no tools
- Researcher still functions without filesystem access, just with reduced capability
- Warning logged: `f"[Orchestrator] WARNING: MCP tools unavailable ({e}), running without external tools"`

**Finding N-9 (GOOD PATTERN)**: Result merging with gap tracking.
- `_merge_parallel_results` cleanly handles timed_out, error, and success per agent
- `gaps` list and confidence footer give users visibility into data completeness
- Markdown formatting with `## Agent Name` sections is presentation-ready

---

## Appendix O — LLM Router Architecture Audit (`src/agents/llm_router.py`)

**File**: `src/agents/llm_router.py` — 10.65 KB, ~254 lines
**Branch**: `feature/CREDITTECH-241864-initial-scaffold`
**Audited**: April 14, 2026

### O.1 Module Purpose

The LLM Router is the brain of Phase 3 financial query routing. It uses a **single LLM completion call** (Claude Haiku via litellm) to decide which specialist agents should handle a financial query. It reads a DynamoDB agent registry for active agents, falls back to static descriptions if the registry is unavailable, and falls back to `kdb-agent` if the LLM response cannot be parsed.

### O.2 Key Constants (Lines 33–90)

| Constant | Purpose |
|----------|---------|
| `_FALLBACK_AGENT = "kdb-agent"` | Default agent when routing fails |
| `_AGENT_DEFAULT_TIMEOUT_MS` | Per-agent timeout defaults (kdb: 90s, amps: 30s, portfolio/cds/etf: 60s, risk-pnl: 90s, financial-orchestrator: 90s) |
| `_AGENT_DESCRIPTIONS` | Static capability descriptions for 7 agents (kdb, amps, portfolio, cds, etf, risk-pnl, financial-orchestrator) |
| `_ROUTER_SYSTEM` | System prompt: "Output valid JSON only — no explanation, no markdown, no other text" |
| `_ROUTER_PROMPT_TEMPLATE` | User prompt with routing rules, Spanish language triggers ('ahora mismo', 'en tiempo real', 'actual'), expected JSON schema |

### O.3 Dataclasses (Lines 93–106)

**AgentConfig**: `id: str`, `priority: Literal["required", "optional"] = "required"`, `timeout_ms: int = 60000`
**RouterDecision**: `agents: list[AgentConfig]`, `strategy: Literal["parallel", "sequential"] = "parallel"`, `reasoning: str = ""`, `fallback_used: bool = False`

### O.4 `route_query()` Function Flow (Lines 109–218)

1. **Import** `config` and `list_all_agents` from a2a registry (lazy imports inside function body)
2. **Build agent descriptions**: Try DynamoDB registry → filter to known agents → enrich with static descriptions. If registry fails, use static descriptions only.
3. **Format prompt** with `_ROUTER_PROMPT_TEMPLATE.format(agent_list=..., query=...)`
4. **Mock mode** (line 155): If `config.LLM_PROVIDER == "mock"`, return kdb-agent immediately (no LLM call)
5. **LLM call via litellm** (lines 163–190):
   - **Ollama path**: `litellm.completion(model=f"ollama/{ollama_model}", ..., format="json", temperature=0, max_tokens=512)`
   - **Anthropic path**: `litellm.completion(model=f"anthropic/{config.ANTHROPIC_FAST_MODEL}", ..., temperature=0, max_tokens=512)` — **NO `format="json"`**
6. **Parse response** (lines 191–196): Strip markdown code fences (``` handling), then `json.loads(raw)`
7. **Extract fields**: `_parse_agents(decision.get("agents", []))`, strategy defaults to "parallel", reasoning defaults to ""
8. **Return** `RouterDecision` with agents, strategy, reasoning
9. **Except** (lines 210–218): Any error → fallback to kdb-agent with `fallback_used=True`

### O.5 `_parse_agents()` Function (Lines 221–254)

Handles two LLM response formats for backward compatibility:
- **String format** (old): `["kdb-agent"]` → validates against known set, assigns "required" priority and default timeout
- **Dict format** (new): `[{"id": "kdb-agent", "priority": "required", "timeout_ms": 90000}]` → validates id, sanitizes priority (must be "required"/"optional"), uses LLM-provided timeout with static default fallback
- **Final fallback**: `return configs or [AgentConfig(id=_FALLBACK_AGENT)]` — if no valid agents parsed, returns kdb-agent

### O.6 DynamoDB Registry Integration (Lines 126–147)

```
try:
    active_agents = list_all_agents()    # DynamoDB scan
except Exception:
    active_agents = []                    # Graceful fallback

if active_agents:
    agent_map = {a["agent_id"]: capabilities for a in active_agents if a["agent_id"] in _AGENT_DESCRIPTIONS}
    # STATIC descriptions OVERRIDE dynamic capabilities for routing quality
    agent_list = f'- "{aid}": {_AGENT_DESCRIPTIONS.get(aid, caps)}' for each agent
else:
    # Pure static fallback
    agent_list = f'- "{aid}": {desc}' for each in _AGENT_DESCRIPTIONS
```

### O.7 Audit Findings

**Finding O-1 (BUG — MEDIUM)**: Anthropic path missing `format="json"`.
- Ollama path (line 178) has `format="json"` forcing JSON output mode
- Anthropic path (lines 181–190) relies only on the system prompt instruction "Output valid JSON only"
- The code fence stripping (lines 192–195) mitigates this for Haiku which tends to wrap JSON in ``` blocks
- **Risk**: Anthropic models may occasionally produce explanatory text alongside JSON, causing `json.loads` to fail and triggering the kdb-agent fallback
- **Fix**: Add `response_format={"type": "json_object"}` to the Anthropic litellm call, or use structured output

**Finding O-2 (DESIGN CONCERN — MEDIUM)**: Dynamic registry filtered by static known set defeats "zero-code" agent addition.
- Line 136: `if a.get("agent_id") in _AGENT_DESCRIPTIONS` — agents in DynamoDB but NOT in the static `_AGENT_DESCRIPTIONS` dict are silently dropped
- Line 229: `known = set(_AGENT_DESCRIPTIONS.keys())` — `_parse_agents` also validates against the static set
- **Impact**: Adding a new agent to DynamoDB alone is NOT sufficient. The router code must also be updated with a static description and default timeout. This contradicts the DynamoDB design goal of "new agents added without code changes."
- **Fix**: Accept any agent_id from DynamoDB that has capabilities defined, even if not in the static map. Use the DynamoDB capabilities as the description when no static one exists.

**Finding O-3 (DESIGN CONCERN — LOW)**: Static descriptions override dynamic capabilities (line 140).
- `_AGENT_DESCRIPTIONS.get(aid, caps)` means the LLM always sees the hand-crafted static description, never the DynamoDB capabilities field
- This is actually **intentional and good** for routing quality — hand-crafted descriptions route better than comma-separated capability lists
- However, if DynamoDB capabilities are updated (e.g., kdb-agent adds new data sources), the router won't reflect it
- **Recommendation**: Log a warning when DynamoDB capabilities differ significantly from static descriptions, to alert developers to update

**Finding O-4 (CODE QUALITY — LOW)**: Dual logging pattern (logger + print).
- Lines 156, 206, 212 all have both `logger.info/warning(...)` AND `print(f"[LLM Router] ...")` for the same event
- Same pattern seen in orchestrator.py (Finding N-4)
- **Fix**: Remove print statements; use structured logging only

**Finding O-5 (CODE QUALITY — LOW)**: `import litellm` inside try block (line 164).
- If litellm is not installed, the entire routing falls back to kdb-agent with a generic error message
- This is acceptable for development flexibility but should be a hard dependency in production
- **Recommendation**: Move to top-level import with a clear error message if missing

**Finding O-6 (ROBUSTNESS — LOW)**: Code fence stripping only handles triple-backtick wrapping.
- Lines 193–195 handle ` ```json\n{...}\n``` ` format
- Does not handle single-backtick or other markdown artifacts
- Haiku rarely produces other formats with `temperature=0`, so risk is minimal

**Finding O-7 (GOOD PATTERN)**: Triple-layer fallback architecture.
- Layer 1: DynamoDB registry → static descriptions (agent list assembly)
- Layer 2: Mock mode bypass for testing without LLM calls
- Layer 3: Any exception → kdb-agent with `fallback_used=True` flag
- The system NEVER throws an exception — it always returns a valid RouterDecision

**Finding O-8 (GOOD PATTERN)**: Backward-compatible agent parsing.
- `_parse_agents` handles both string lists (old format) and dict lists (new format)
- Invalid priority values sanitized to "required"
- Unknown agent IDs silently skipped (no crash)
- Empty result → kdb-agent fallback via `configs or [AgentConfig(id=_FALLBACK_AGENT)]`

**Finding O-9 (GOOD PATTERN)**: Deterministic routing with `temperature=0`.
- Both Ollama and Anthropic paths use `temperature=0` ensuring consistent routing for identical queries
- `max_tokens=512` is appropriate for a small JSON response (typical response is ~100 tokens)

---

## Appendix P — Agent Support Modules Audit (model_factory, tools, prompt_registry, researcher, synthesizer)

**Files**: 5 modules in `src/agents/` — total ~12.6 KB, ~351 lines
**Branch**: `feature/CREDITTECH-241864-initial-scaffold`
**Audited**: April 14, 2026

### P.1 `model_factory.py` (3.19 KB, 87 lines) — LLM Provider Abstraction

**Purpose**: Factory returning Strands-compatible model objects based on `config.LLM_PROVIDER`. Implements **tiered model strategy**:
- `get_strands_model()` → main model (Sonnet / larger Ollama) for orchestrators and synthesizers
- `get_strands_fast_model()` → fast model (Haiku / smaller Ollama) for tool-heavy sub-agents (KDB, AMPS)

**Four LLM Provider Paths** (identical structure in both functions):

| Provider | Model Class | Model ID | Auth |
|----------|-----------|----------|------|
| `mock` | `LiteLLMModel` | `openai/gpt-3.5-turbo` | `api_key="mock-key"`, `mock_response=_MOCK_RESPONSE` |
| `ollama` | `LiteLLMModel` | `ollama/{OLLAMA_MODEL}` | `api_base=OLLAMA_BASE_URL`, `api_key="ollama"` |
| `anthropic` | `LiteLLMModel` | `anthropic/{ANTHROPIC_MODEL}` | `api_key=ANTHROPIC_API_KEY` |
| `else` (bedrock) | `BedrockModel` | `BEDROCK_MODEL` | IAM role auth, `region_name=AWS_REGION` |

**Fast model config variables** (key difference from main model):
- Ollama: `OLLAMA_FAST_MODEL or OLLAMA_MODEL` (fallback if fast not set)
- Anthropic: `ANTHROPIC_FAST_MODEL` (Haiku)
- Bedrock: `BEDROCK_FAST_MODEL`

**Design Note**: Lazy imports (`from strands.models... import` inside function body) — intentional to avoid import errors when a provider's SDK is not installed.

### P.2 `tools.py` (1.9 KB, 62 lines) — Strands Agent Tools

**Purpose**: Two `@tool`-decorated functions shared across Strands agents.

**`search_knowledge_base(query: str) -> str`** (lines 12–40):
- Calls `get_retriever()` from `src.rag.retriever`
- Empty KB check: `retriever.count() == 0` → returns "Knowledge base is empty"
- Retrieves documents: `retriever.retrieve(query)`
- Formats results as numbered list: `[1] [source: filename]\n{text}` separated by `---`
- **Note**: Expects `doc["source"]` and `doc["text"]` keys — tight coupling to retriever's return format

**`summarize_findings(findings: str) -> str`** (lines 43–62):
- **POC placeholder** — comments explicitly state: "For the POC the orchestrating agent will handle summarization through its own LLM reasoning; this tool is a placeholder showing the pattern."
- Implementation: splits text into lines, prepends bullet points (`• {line}`), caps at 20 lines
- No actual LLM-based summarization — the agent's reasoning loop does the real work

### P.3 `prompt_registry.py` (3.99 KB, 107 lines) — Langfuse Prompt Management

**Purpose**: Decouples agent system prompts from code — prompts stored and versioned in Langfuse, editable without redeployment.

**Architecture**:
1. **Singleton Langfuse client** (`_get_client()`, lines 38–61) — thread-safe double-checked locking with `threading.Lock()`
2. **In-process cache** (`_prompt_cache: dict[str, str]`) — permanent for process lifetime
3. **Self-seeding** — on first call, if prompt doesn't exist in Langfuse, creates it from the hardcoded default

**`get_system_prompt(name, default) -> str`** Flow (lines 64–107):
1. **Fast path**: Return from `_prompt_cache` if cached
2. **Client check**: If Langfuse disabled/unavailable → return hardcoded `default`
3. **Try load**: `client.get_prompt(name, label="production", cache_ttl_seconds=300)` → `.compile()` → cache + return
4. **Self-seed on miss**: `client.create_prompt(name=name, prompt=default, labels=["production"], config={"source": "auto-seeded"})` — creates the prompt in Langfuse so subsequent restarts/replicas load it
5. **Final fallback**: If seeding also fails → return hardcoded `default`

**Graceful degradation** (three levels):
- `OBSERVABILITY_ENABLED=false` → always returns default (no Langfuse call)
- Langfuse unreachable → logs warning, returns default
- Prompt not found after seeding attempt → returns default

### P.4 `researcher.py` (1.83 KB, 52 lines) — Research Agent Factory

**Purpose**: Factory function creating a Strands Agent for research tasks.

```
def create_researcher(extra_tools=None) -> Agent:
    tools = [search_knowledge_base, summarize_findings]
    if extra_tools: tools.extend(extra_tools)
    return Agent(model=get_strands_model(), system_prompt=RESEARCHER_SYSTEM_PROMPT, tools=tools)
```

**System prompt** instructs the agent to: search local KB first → web search (brave_web_search) → fetch URLs → read local docs → summarize findings → return structured report (Key facts, Sources, Gaps).

**Note**: Uses `get_strands_model()` (main/Sonnet tier), not the fast model.

### P.5 `synthesizer.py` (1.64 KB, 43 lines) — Synthesis Agent Factory

**Purpose**: Factory function creating a **tool-less** Strands Agent for synthesis.

```
def create_synthesizer() -> Agent:
    return Agent(model=get_strands_model(), system_prompt=SYNTHESIZER_SYSTEM_PROMPT, tools=[])
```

**System prompt** instructs: receive original question + specialist agent findings → synthesize clear answer → apply confidence tags `[HIGH]` (confirmed by required agent) / `[LOW]` (secondary sources, estimated, or agent timed out) → flag missing data from timed out agents.

**Key design**: No tools — synthesizer is pure LLM reasoning over pre-collected results.

### P.6 Audit Findings

**Finding P-1 (BUG — LOW)**: Bedrock is the `else` default in model_factory.py — silent misrouting.
- `get_strands_model()` line 51: `else:` → BedrockModel
- Any typo in `LLM_PROVIDER` (e.g., "antrhopic", "Anthropic", "aws") silently routes to Bedrock
- Bedrock requires IAM role auth, which will fail in local dev environments with a cryptic boto3 error
- **Fix**: Add explicit `elif config.LLM_PROVIDER == "bedrock":` and raise `ValueError(f"Unknown LLM_PROVIDER: {config.LLM_PROVIDER}")` in the else block

**Finding P-2 (CODE QUALITY — LOW)**: ~60% code duplication between `get_strands_model()` and `get_strands_fast_model()`.
- Both functions are ~30 lines each with identical structure; only the config variable differs
- **Fix**: Extract common logic into `_build_model(main: bool = True)` helper that selects the appropriate config variable per provider

**Finding P-3 (DESIGN NOTE)**: `summarize_findings` tool is a placeholder.
- The tool name suggests LLM-powered summarization, but implementation is a naïve line splitter with bullet formatting
- Comments explicitly acknowledge this is POC-level
- The Strands agent's own reasoning loop handles actual synthesis — the tool just reformats text
- **Risk**: If future developers treat this as real summarization, they may be surprised by the quality
- **Recommendation**: Either rename to `format_as_bullets` to match actual behavior, or implement actual summarization via a secondary LLM call

**Finding P-4 (DESIGN CONCERN — MEDIUM)**: Process-lifetime prompt cache shadows Langfuse TTL.
- `_prompt_cache` dict (line 35) has **no TTL** — once a prompt is cached in the process, it never refreshes
- Langfuse's `cache_ttl_seconds=300` (line 86) only affects the Langfuse SDK's internal cache
- **Impact**: Prompt changes made in Langfuse UI won't take effect until the Fargate task is restarted/redeployed
- **Fix**: Add a TTL to `_prompt_cache` (e.g., store `(text, timestamp)` tuples and expire after 5 minutes), or remove the process cache entirely and rely on Langfuse SDK's built-in caching

**Finding P-5 (GOOD PATTERN)**: Self-seeding prompt registry.
- First-run auto-creation of prompts in Langfuse means: (1) code always has a working fallback, (2) Langfuse UI is automatically populated for non-technical users to edit, (3) `config={"source": "auto-seeded"}` metadata helps track which prompts were manually edited vs auto-created
- This is an excellent pattern for onboarding new environments

**Finding P-6 (GOOD PATTERN)**: Thread-safe Langfuse singleton with double-checked locking.
- `_client_lock = threading.Lock()` with check-lock-check pattern prevents race conditions during multi-threaded startup
- Graceful degradation chain (OBSERVABILITY_ENABLED → keys present → Langfuse init) means the system never fails to start regardless of Langfuse availability

**Finding P-7 (GOOD PATTERN)**: Tiered model strategy (main vs fast).
- Orchestrators/synthesizers use Sonnet (better reasoning) while tool-heavy sub-agents use Haiku (faster, cheaper)
- This directly maps to the financial query architecture: router (Haiku) → specialist agents (Haiku) → synthesis (Sonnet)
- Ollama fast model has `OLLAMA_FAST_MODEL or OLLAMA_MODEL` fallback for local dev with only one model

**Finding P-8 (GOOD PATTERN)**: Extensible researcher with `extra_tools` parameter.
- `create_researcher(extra_tools=None)` allows injecting additional tools at call sites without modifying the factory
- Base tools (search_knowledge_base, summarize_findings) always included; caller can add domain-specific tools

---

## Appendix Q — Financial Orchestrators + A2A Audit (`financial_orchestrator.py`, `financial_orchestrator_v2.py`, `a2a/client.py`, `a2a/registry.py`)

**Files audited**: 4 files, ~474 lines total
- `src/agents/financial_orchestrator.py` (6.35 KB, 155 lines) — Phase 1 in-process orchestrator
- `src/agents/financial_orchestrator_v2.py` (6.38 KB, 156 lines) — Phase 2 A2A orchestrator
- `src/a2a/client.py` (2.49 KB, 79 lines) — Google A2A HTTP client
- `src/a2a/registry.py` (3.74 KB, ~120 lines) — DynamoDB agent registry

### Architecture Overview

The financial orchestrator is a **domain-specific sub-orchestrator** called by the top-level `orchestrator.py` (Appendix N). It implements the **agent-as-tool pattern** using AWS Strands: specialist agent modules (`kdb_agent`, `amps_agent`) are wrapped as `@tool` functions and given to a Strands `Agent` that decides which tools to call based on the user's query.

**Three data sources:**
1. **KDB+ historical** (`query_kdb_history` tool) — 6+ months of Bond RFQ data (hit rates, spreads, volumes)
2. **AMPS live** (`query_amps_data` tool) — Real-time orders, positions, market quotes via pub/sub
3. **RAG knowledge base** (`search_knowledge_base` tool) — Domain documentation, strategy definitions

**System prompt** is identical in v1 and v2 (~74 lines): Senior Bond Trading Analyst persona with decision logic table (historical→KDB, live→AMPS, both→call both, conceptual→KB only), proactive defaults (6 months, HY desk, avg_hit_rate), structured response format (data sources, key findings, analysis, confidence level), and bond domain knowledge (desk types HY/IG/EM/RATES, metric definitions).

### v1 vs v2 Differences

| Aspect | v1 (financial_orchestrator.py) | v2 (financial_orchestrator_v2.py) |
|--------|-------------------------------|----------------------------------|
| Tool invocation | `from src.agents.kdb_agent import run_kdb_agent` (in-process) | `call_agent_sync(endpoint, query, timeout=config.A2A_TIMEOUT)` (HTTP) |
| Agent discovery | Direct Python import | `get_endpoint("kdb-agent", config.KDB_AGENT_URL)` → DynamoDB registry with fallback |
| Model tier | `get_strands_model()` (Sonnet/main) | `get_strands_fast_model()` (Haiku/fast) |
| Scalability | Monolithic — agents share process | Distributed — agents can be on different hosts/regions |
| Function name | `run_financial_orchestrator()` | `run_financial_orchestrator_v2()` |

### A2A Client Protocol (client.py)

Implements the **Google A2A (Agent-to-Agent) protocol** over HTTP:
- Builds `A2ATask` with UUID, `TaskMessage(parts=[MessagePart(text=query)])`, sessionId
- POSTs to `{endpoint}/a2a` via `httpx.AsyncClient`
- Validates response as `A2AResult`, extracts `artifacts[0].parts[0].text`
- **Never raises exceptions** — all errors return descriptive strings (timeout, connection, failed status)
- `call_agent_sync()` wraps the async version with `asyncio.run()` for use in synchronous Strands `@tool` functions

### Agent Registry (registry.py)

DynamoDB-backed service discovery with **TTL-based health tracking**:
- Table: `agentic-ai-staging-agent-registry`, PK: `agent_id`, GSI: `desk_name`
- `register_agent(agent_id, endpoint, capabilities, desk_names)` — puts item with status="healthy", ttl=now+120s
- `deregister_agent(agent_id)` — delete on shutdown
- `discover_agent(agent_id)` — get_item by PK, returns full dict or None
- `get_endpoint(agent_id, fallback)` — discovers agent, checks status="healthy", returns endpoint or falls back to config env var
- `list_all_agents()` — table scan filtering healthy + unexpired TTL (used by LLM Router Phase 3)
- LocalStack support via `AWS_ENDPOINT_URL` env var

### Audit Findings

**Finding Q-1 (CONCERN — model tier inconsistency between v1 and v2)**: v1 orchestrator uses `get_strands_model()` (Sonnet) while v2 uses `get_strands_fast_model()` (Haiku). This means v2 uses a less capable model for the same orchestration decisions. The financial orchestrator needs to decide which data sources to query and synthesize results — arguably this warrants the more capable model. If the intent is to use the fast model, v1 should match; if orchestrators need Sonnet, v2 should be updated.

**Finding Q-2 (CONCERN — asyncio.run() in call_agent_sync creates new event loop per call)**: `call_agent_sync()` calls `asyncio.run(call_agent(...))` which creates and destroys an event loop on every invocation. If the financial orchestrator calls both KDB and AMPS agents sequentially, this is two full event loop lifecycle cycles. Additionally, `asyncio.run()` will fail if called from within an already-running event loop (e.g., if the FastAPI server is using asyncio). Consider using `loop.run_until_complete()` or making the orchestrator itself async.

**Finding Q-3 (CONCERN — system prompt duplication between v1 and v2)**: The `_SYSTEM_PROMPT` string (~74 lines) is copy-pasted identically in both files. Changes to the prompt require editing both files. Should be extracted to a shared module or loaded from `prompt_registry.py` (which already exists for this purpose).

**Finding Q-4 (CONCERN — no retry logic in A2A client)**: `call_agent_sync()` makes a single HTTP call with no retry. Network-level transient failures (502, 503, connection reset) will immediately return error strings. For production bond trading analytics, at least one retry with backoff would improve reliability.

**Finding Q-5 (CONCERN — registry TTL relies on agent healthcheck renewal)**: The registry sets `_TTL_SECONDS = 120` and expects agents to call `register_agent()` periodically to renew their TTL. If an agent process crashes without calling `deregister_agent()`, it remains "healthy" in the registry for up to 120 seconds, during which the orchestrator will attempt to call it and get connection errors. The `get_endpoint()` fallback to config URL mitigates this, but there's a window of false-positive discovery.

**Finding Q-6 (CONCERN — registry table name hardcoded to staging)**: `_TABLE = os.getenv("AGENT_REGISTRY_TABLE", "agentic-ai-staging-agent-registry")` — the default table name contains "staging". In production, this must be overridden via env var. If the env var is missing in prod, it will silently use the staging table.

**Finding Q-7 (GOOD PATTERN)**: Agent-as-tool pattern with clean separation of concerns.
- Tools are thin wrappers (2-3 lines) that delegate to specialist modules
- The LLM decides which tools to call based on the system prompt's decision logic
- v2 evolution to HTTP-based calls is a clean architectural upgrade — same pattern, different transport

**Finding Q-8 (GOOD PATTERN)**: Registry with graceful fallback to config env vars.
- `get_endpoint(agent_id, fallback)` tries DynamoDB first, falls back to config URL
- Supports local dev (LocalStack), staging, and production via env vars
- Clean separation: registry for dynamic discovery, config for static fallback

**Finding Q-9 (GOOD PATTERN)**: RAG context injection from LangGraph into financial orchestrator.
- `run_financial_orchestrator(query, rag_context="")` accepts pre-retrieved context from the LangGraph retrieve node
- Injects it as `[Pre-retrieved knowledge base context]\n{rag_context}` appended to the query
- This avoids duplicate RAG retrieval — the LangGraph already fetched relevant docs

**Finding Q-10 (GOOD PATTERN)**: A2A client never raises — returns error strings.
- All exception paths (`TimeoutException`, `ConnectError`, generic `Exception`) return descriptive f-strings
- Callers (the LLM via @tool) see the error as tool output and can reason about it
- Prevents agent crashes from propagating to the orchestrator

---

## Appendix R: Infrastructure Configuration Audit — config.py, mcp_clients.py, observability.py (646 lines total)

**Files reviewed**: `src/config.py` (165 lines, 8.37 KB), `src/mcp_clients.py` (285 lines, 9.08 KB), `src/observability.py` (196 lines, 7.78 KB)

### R.1 — Configuration Architecture (src/config.py)

**Finding R-1 (ISSUE — Medium)**: No model tiering unless env vars explicitly set.
- `ANTHROPIC_MODEL` and `ANTHROPIC_FAST_MODEL` both default to `"claude-haiku-4-5"`
- This means the "main" model (used for complex reasoning) and the "fast" model (used for routing/classification) are identical by default
- Bedrock is properly tiered: main=`us.anthropic.claude-sonnet-4-20250514`, fast=`us.anthropic.claude-haiku-4-5-20251001`
- **Recommendation**: Default `ANTHROPIC_MODEL` to Sonnet for proper cost/quality tiering, matching Bedrock defaults

**Finding R-2 (ISSUE — Low)**: Config singleton via module-level instance, not thread-safe lazy init.
- `config = Settings()` at module bottom executes on first import
- All consumers import with `from src.config import config`
- Works correctly for single-process FastAPI, but if `Settings()` ever needs async init or conditional logic, this pattern blocks it
- **Recommendation**: Acceptable for current architecture; note if moving to multi-process workers

**Finding R-3 (GOOD PATTERN)**: Comprehensive env-var surface with sensible defaults.
- 30+ configuration knobs all loaded via `os.getenv()` with defaults
- Boolean flags follow consistent `"true"/"false"` string pattern
- Multi-provider LLM support: `LLM_PROVIDER` switch for anthropic/bedrock/ollama/mock
- `GRAPH_RECURSION_LIMIT` defaults to 25 (used by LangGraph workflow)
- `MAX_SEARCH_RESULTS` = 5, `CHUNK_SIZE` = 1000, `CHUNK_OVERLAP` = 200 for RAG

**Finding R-4 (ISSUE — Low)**: Tiered timeout values hardcoded in config, not in agent definitions.
- `AGENT_TIMEOUT_AMPS=30`, `AGENT_TIMEOUT_KDB=90`, `AGENT_TIMEOUT_FINANCIAL=90`, `AGENT_TIMEOUT_PORTFOLIO=60`, `AGENT_TIMEOUT_CDS=60`, `AGENT_TIMEOUT_ETF=60`, `AGENT_TIMEOUT_RISK_PNL=90`
- Timeouts are per-agent but defined in global config rather than co-located with agent definitions
- Creates coupling: adding a new agent requires touching config.py
- **Recommendation**: Consider agent-level timeout declarations with config override capability

### R.2 — MCP Client Management (src/mcp_clients.py)

**Finding R-5 (ARCHITECTURE INSIGHT)**: Two-tier MCP client architecture — general vs. domain-specific.
- `open_mcp_tools(docs_path)` context manager bundles 3 general clients: Brave Search, Fetch, Filesystem
- Plus 2 "Phase 1" domain clients: AMPS, KDB (conditionally included via `AMPS_ENABLED`/`KDB_ENABLED` flags)
- 3 "Phase 3" domain clients have separate context managers: `open_portfolio_tools()`, `open_cds_tools()`, `open_etf_tools()`
- **Key**: Phase 3 clients are NOT included in `open_mcp_tools()` — they are managed independently by their respective Strands agent factories
- This split reflects the Phase 1→3 evolution: general tools go through the monolithic context manager, while newer domain agents manage their own MCP lifecycle

**Finding R-6 (ISSUE — Medium)**: Inconsistent enablement defaults across domain MCP clients.
- AMPS_ENABLED defaults to `"false"`, KDB_ENABLED defaults to `"false"`
- PORTFOLIO_ENABLED defaults to `"true"`, CDS_ENABLED defaults to `"true"`, ETF_ENABLED defaults to `"true"`
- This means a fresh deployment with no env vars configured will have Portfolio/CDS/ETF servers attempting to start, but AMPS/KDB disabled
- If the MCP server scripts aren't present or configured, the Phase 3 agents will fail silently (due to broad exception handling)
- **Recommendation**: Either default all to `"false"` (explicit opt-in) or document the asymmetry clearly

**Finding R-7 (ISSUE — Medium)**: Broad `except Exception` swallows MCP server startup failures.
- In `open_mcp_tools()` lines 148-157: each client start is wrapped in try/except that prints a warning but continues
- This is a deliberate graceful-degradation pattern, but it means a misconfigured AMPS or KDB server silently disappears
- The print goes to stdout, not to the observability stack or structured logging
- **Recommendation**: Log to the OTEL tracing system or at minimum use `logging.warning()` with structured context (server name, error type)

**Finding R-8 (ISSUE — Low)**: `env={**os.environ}` passes full host environment to subprocess MCP servers.
- All 8 `StdioServerParameters` calls pass `env={**os.environ}`
- This means MCP server subprocesses inherit ALL environment variables, including secrets like `LANGFUSE_SECRET_KEY`, `DYNATRACE_API_TOKEN`, AWS credentials
- For the Python-based servers (amps, kdb, portfolio, cds, etf), they need some env vars but not all
- **Recommendation**: Construct minimal env dicts per server, passing only required variables

**Finding R-9 (GOOD PATTERN)**: Conditional client creation based on tool availability.
- `open_mcp_tools()` checks `shutil.which("npx")` and `shutil.which("uvx")` before creating Brave/Fetch clients
- This prevents crashes in environments where Node.js or uv aren't installed
- The filesystem client always starts (pure Python path), AMPS/KDB check their enabled flags
- Yields tool count: `[MCP] {len(all_tools)} external tools loaded from {started}/{len(clients)} servers.`

### R.3 — Observability Stack (src/observability.py)

**Finding R-10 (GOOD PATTERN)**: Well-designed dual Langfuse integration serves complementary purposes.
- **Layer 1**: OTEL traces via `OTLPSpanExporter` → Langfuse `/api/public/otel/v1/traces` endpoint
  - Captures ALL spans including Strands agent calls, MCP tool invocations, LangChain operations
  - Uses Base64-encoded `public_key:secret_key` auth header
- **Layer 2**: `get_langfuse_callback()` returns a LangChain `CallbackHandler`
  - Passed to `graph.invoke(input, config={"callbacks": [handler]})` in orchestrator
  - Provides the **graph-level view** in Langfuse UI — shows LangGraph node transitions, state changes
- These are NOT redundant: OTEL gives individual span telemetry, CallbackHandler gives workflow topology
- This is the correct pattern for LangGraph + external agent observability

**Finding R-11 (GOOD PATTERN)**: Phoenix auto-instrumentation for zero-config LangChain tracing.
- `LangChainInstrumentor().instrument(tracer_provider=provider)` from `openinference.instrumentation.langchain`
- Automatically wraps all LangChain/LangGraph calls with OTEL spans — no manual instrumentation needed
- Combined with the Langfuse OTEL exporter, this creates a complete trace pipeline with no code changes to the agents

**Finding R-12 (GOOD PATTERN — CORRECTED)**: `exporters_added` counter properly tracks active backends.
- Line 63: `exporters_added = 0` initialized
- Line 77: `exporters_added += 1` after Phoenix `provider.add_span_processor()`
- Line 102: `exporters_added += 1` after Langfuse `provider.add_span_processor()`
- Line 124: `exporters_added += 1` after Dynatrace `provider.add_span_processor()`
- Line 132: `if exporters_added == 0:` — correctly guards against no-exporter scenario, warns and returns
- Line 139: `trace.set_tracer_provider(provider)` — only called when at least 1 exporter is active
- Each exporter block also has `try/except ImportError` to gracefully skip if `opentelemetry-exporter-otlp-proto-http` isn't installed
- **Note**: Initial visual read in previous session missed the `+= 1` lines — verified on re-read. Counter works correctly.

**Finding R-13 (ISSUE — Low)**: Triple import of `OTLPSpanExporter` — imported once at the function level.
- `from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter` appears once in function body
- Used 3 times (Phoenix, Langfuse, Dynatrace exporters)
- Single import is correct — the "triple import" observation from earlier was about 3 usages, not 3 import statements
- **Status**: No issue — this was a false positive from the visual read

**Finding R-14 (GOOD PATTERN)**: Enterprise-grade multi-backend telemetry architecture.
- Three simultaneous OTEL backends: Phoenix (dev/debug), Langfuse (LLM-specific), Dynatrace (enterprise APM)
- Each is independently conditional — any combination of 0-3 backends can be active
- `BatchSpanProcessor` for all three ensures non-blocking trace export
- Service name `"agentic-ai-system"` provides consistent identification across all backends
- Dynatrace uses `Api-Token` auth header matching JPMC enterprise APM patterns

### REMAINING AUDIT BACKLOG (Updated April 14, 2026):
- ~~**`src/agents/llm_router.py`** (10.65 KB) — LLM Router~~ ✅ **COMPLETED → Appendix O**
- ~~**`src/agents/model_factory.py`** (3.19 KB) — Model factory~~ ✅ **COMPLETED → Appendix P**
- ~~**`src/agents/tools.py`** (1.9 KB) — Strands tools~~ ✅ **COMPLETED → Appendix P**
- ~~**`src/agents/prompt_registry.py`** (3.99 KB) — Prompt management~~ ✅ **COMPLETED → Appendix P**
- ~~**`src/agents/researcher.py`** (1.83 KB) — Research agent factory~~ ✅ **COMPLETED → Appendix P**
- ~~**`src/agents/synthesizer.py`** (1.64 KB) — Synthesis agent factory~~ ✅ **COMPLETED → Appendix P**
- ~~**`src/agents/financial_orchestrator.py`** (6.35 KB) — Phase 1 in-process financial orchestrator~~ ✅ **COMPLETED → Appendix Q**
- ~~**`src/agents/financial_orchestrator_v2.py`** (6.38 KB) — Phase 2 variant~~ ✅ **COMPLETED → Appendix Q**
- **`src/agents/`** (other files) — Domain specialist agents (amps, cds, etf, kdb, portfolio, risk_pnl)
- **`src/a2a/parallel_client.py`** — A2A parallel agent caller (AgentResult dataclass, call_agents_parallel_sync)
- ~~**`src/a2a/client.py`** — A2A single agent caller (call_agent_sync)~~ ✅ **COMPLETED → Appendix Q**
- ~~**`src/a2a/registry.py`** — Agent registry (get_endpoint)~~ ✅ **COMPLETED → Appendix Q**
- ~~**`src/config.py`** (8.37 KB) — Runtime config including `GRAPH_RECURSION_LIMIT`~~ ✅ **COMPLETED → Appendix R**
- **`src/rag/retriever.py`** — ChromaDB retriever, `get_retriever()` factory
- ~~**`src/mcp_clients.py`** (9.08 KB) — MCP gateway client, `open_mcp_tools()`~~ ✅ **COMPLETED → Appendix R**
- ~~**`src/observability.py`** (7.78 KB) — Langfuse integration~~ ✅ **COMPLETED → Appendix R**
- **`src/api/`**, **`src/services/`**, **`src/mcp_gateway/`** — Remaining source directories
- `scripts/` folder — Onboarding, ingestion, utilities
- `tests/` folder — Test coverage
- `autonomous_jobs/` — Scheduled tasks
- `requirements.txt` / `pyproject.toml` — Dependencies
- `chroma_db/` contents — Verify vs carson_kb/
- `../mcp-servers/` (19 servers) — Individual MCP implementations
- **`high-touch-terraform-agentic-ai` — environments/ and variables/ folders** (not yet read)
- **`BEDROCK_CONFIG.md`** (10.04 KB) — Bedrock integration details not yet read
- **Remaining terraform repos** — terraform-central, terraform-base, terraform-lambdas deep-reads (13 repos remain)
- **high-touch-terraform-fargate — iam.tf, locals.tf, providers.tf, security_groups.tf** (small files not yet read)

---

*Generated by Claude Opus 4.6 architectural review — April 2026*
*Updated with concrete config.yaml audit findings — April 13, 2026*
*Updated with fix_chromadb.py, send_carson_reply.py, config_template.yaml deep-read — April 13, 2026*
*Updated with carson_service.py full audit (75.72KB, 54 functions, 28+ endpoints) — April 13, 2026*
*Updated with ACAMPS repo inventory (40+ repos) and high-touch-terraform-agentic-ai full audit — April 13, 2026*
*Updated with high-touch-terraform-fargate full audit + CORRECTED deployment dependency map — April 14, 2026*
*Updated with LangGraph architecture audit (state.py, workflow.py, nodes.py) from high-touch-agentic-ai-api — April 14, 2026*
*Updated with Orchestrator architecture audit (orchestrator.py, 257 lines, 3-phase financial + general pipeline) — April 14, 2026*
*Updated with LLM Router architecture audit (llm_router.py, 254 lines, Haiku routing + DynamoDB registry + triple fallback) — April 14, 2026*
*Updated with Agent Support Modules audit (model_factory + tools + prompt_registry + researcher + synthesizer, 351 lines) — April 14, 2026*
*Updated with Financial Orchestrators + A2A audit (financial_orchestrator v1/v2, a2a/client, a2a/registry, 474 lines) — April 14, 2026*
*Updated with Infrastructure Config audit (config.py + mcp_clients.py + observability.py, 646 lines, 14 findings) — April 14, 2026*
*For the Carson Multi-Agent System v2.1.0 (high-touch-agent-prompts + high-touch-terraform-agentic-ai + high-touch-terraform-fargate repos)*
