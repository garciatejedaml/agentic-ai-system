# Carson Full Review v2 — Implementation Specification

**Purpose:** This document is a self-contained specification for an AI copilot (Opus) to execute the Carson multi-agent system refactor. It contains all context, patterns, bugs fixed, and tasks — organized for parallel execution.

**Repo:** `I:\repositories\high-touch-agent-prompts\langgraph-system\`
**Runtime:** AWS Bedrock via CDAO SDK (NOT boto3) on JPMC Citrix VDI

---

## 0. Critical Rules (Read First)

1. **NEVER use boto3 directly.** All Bedrock calls → `cdao.bedrock_byoa_invoke_model(data, payload)`
2. **Anthropic Messages API format only (snake_case).** The method `converse()` in `bedrock_client.py` actually calls InvokeModel, NOT the Bedrock Converse API. All responses come back in Anthropic format: `tool_use`, `tool_result`, `tool_use_id`, `stop_reason`, `id`. **Never** use Converse camelCase: ~~`toolUse`~~, ~~`toolResult`~~, ~~`toolUseId`~~, ~~`stopReason`~~.
3. **`agent_response` is a string, not a dict.** Every agent must return `{"agent_response": "human-readable string"}`.
4. **CDAO SDK config** (hardcoded, same everywhere):
```python
data = {
    "AWSAccountNumber": "043309362186",
    "AWSRegion": "us-east-1",
    "WorkspaceID": "905183",
    "isExecutionRole": False
}
model_id = "arn:aws:bedrock:us-east-1:043309362186:application-inference-profile/8p2aoh7kcfwe"
```

---

## 1. Bugs Fixed (Context — Do NOT Re-Fix)

These are already applied on the VDI but the workspace copy may be stale:

| Bug | File | Fix Applied |
|-----|------|-------------|
| Tools passed without conversion | `bedrock_client.py` L439 | `request_body["tools"] = self._convert_tools_to_anthropic(tools)` |
| JIRA_TOOLS wrapped in toolSpec | `jira_agent.py` L264 | Changed `[{"toolSpec": t} for t in JIRA_TOOLS]` → `JIRA_TOOLS` |
| tool_use block detection (Converse vs Anthropic) | `jira_agent.py` L281 | `block.get("type") in ("toolUse", "tool_use")` |
| tool_use_id field name | `jira_agent.py` L285 | `tool_use.get("toolUseId", "") or tool_use.get("id", "")` |
| tool_result format in messages | `jira_agent.py` L294-298 | `"type": "tool_result"`, `"tool_use_id"`, `"content": tool_result` |
| Jira OAuth token empty | `HumanAuthentication.py` | **NOT FIXED** — OAuth flow issue, separate from code |

---

## 2. Architecture Overview

```
carson_service.py (Flask :8765)
  └─ workflow.py (LangGraph)
       ├─ router_node.py      → intent detection, picks agent
       ├─ agents/
       │   ├─ jira_agent.py   ← GOLDEN TEMPLATE (tool-use works)
       │   ├─ git_agent.py
       │   ├─ build_agent.py
       │   ├─ deploy_agent.py
       │   ├─ docs_agent.py
       │   ├─ terraform_agent.py
       │   └─ general_agent.py
       ├─ inspector_node.py   → quality review
       └─ response synthesizer → final_response
```

**Bedrock client chain:**
```
agent → bedrock_client.py::converse()
  → _convert_tools_to_anthropic()  (Converse→Anthropic format)
  → builds Anthropic Messages API body
  → cdao.bedrock_byoa_invoke_model(data, payload)
  → response in Anthropic format (snake_case)
```

---

## 3. Golden Template: jira_agent.py (FIXED version)

This is the reference implementation. All other agents with tool-use MUST follow this exact pattern.

### 3.1 Tool Definition Format (Anthropic)
```python
TOOLS = [
    {
        "name": "tool_name",
        "description": "What it does",
        "input_schema": {           # NOT "inputSchema"
            "type": "object",
            "properties": { ... },
            "required": [...]
        }
    }
]
```

### 3.2 Agent Node Function Pattern
```python
def agent_node(state: CarsonState) -> CarsonState:
    user_request = state.get("user_request", "")
    tool_results_collected = []
    bedrock = get_bedrock_client()

    system_prompt = "..."  # Agent-specific
    messages_for_bedrock = [{"role": "user", "content": user_request}]

    max_iterations = 5
    iteration = 0
    agent_response = ""

    while iteration < max_iterations:
        iteration += 1

        response = bedrock.converse(
            modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
            system=[{"text": system_prompt}],
            messages=messages_for_bedrock,
            toolConfig={"tools": TOOLS}  # Pass directly, no wrapping
        )

        stop_reason = response["stopReason"]
        response_message = response["output"]["message"]
        messages_for_bedrock.append(response_message)

        if stop_reason == "end_turn":
            for block in response_message.get("content", []):
                if "text" in block:
                    agent_response += block.get("text", "")
            break

        elif stop_reason == "tool_use":
            tool_results = []
            for block in response_message.get("content", []):
                # Handle BOTH Converse and Anthropic format responses
                if block.get("type") in ("toolUse", "tool_use") or "toolUse" in block:
                    tool_use = block if "name" in block else block.get("toolUse", {})
                    tool_name = tool_use.get("name", "")
                    tool_input = tool_use.get("input", {})
                    tool_use_id = tool_use.get("toolUseId", "") or tool_use.get("id", "")

                    tool_result = execute_tool(tool_name, tool_input)
                    tool_results_collected.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "result": tool_result
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": tool_result
                    })

            messages_for_bedrock.append({
                "role": "user",
                "content": tool_results
            })
        else:
            break

    return {
        **state,
        "agent_response": agent_response,
        "tool_results_collected": tool_results_collected,
        "current_agent": "agent_name"
    }
```

### 3.3 Key Differences from Original (Converse format)

| Field | Converse (OLD/WRONG) | Anthropic (CORRECT) |
|-------|---------------------|---------------------|
| Tool block type | `"toolUse"` | `"tool_use"` |
| Tool use ID field | `"toolUseId"` | `"id"` |
| Tool result type | `"toolResult"` | `"tool_result"` |
| Tool result ID field | `"toolUseId"` | `"tool_use_id"` |
| Tool result content | `[{"type":"text","text":"..."}]` | `"string"` |
| Stop reason | `"stopReason"` | `"stop_reason"` |

**NOTE:** The current code handles BOTH formats for robustness (the `or` checks). This is intentional — keep it until the `converse()` method is fully refactored.

---

## 4. Tasks — Parallelizable Work Streams

### Stream A: Unify Response Format in bedrock_client.py
**File:** `carson_agents/bedrock_client.py`
**Goal:** Rename `converse()` → `invoke()` and ensure consistent Anthropic format output.

1. Rename method `converse()` → `invoke()` (or `chat()`)
2. Update all callers across all agent files
3. Ensure `_convert_tools_to_anthropic()` is always called (already done on L439)
4. Add response normalization: if response has `stop_reason`, map to `stopReason` for backward compat OR update all consumers. Pick one direction — Anthropic format preferred.
5. Add error handling for empty CDAO responses:
```python
response = cdao.bedrock_byoa_invoke_model(self.data, payload)
body = response.get("body")
if not body:
    raise Exception("Empty response from Bedrock. Check AWS credentials.")
raw = body.read()
if not raw:
    raise Exception("Empty response body from Bedrock.")
result = json.loads(raw)
```

### Stream B: Update All Agents to Golden Template
**Files:** `carson_agents/agents/*.py` (all 7 agents)
**Goal:** Every agent follows the jira_agent pattern.

For each agent:
1. Ensure tools are defined in Anthropic format (`input_schema`, not `inputSchema`)
2. Pass tools directly: `toolConfig={"tools": TOOLS}` — no `{"toolSpec": t}` wrapping
3. Tool-use loop handles both formats (the `or` pattern from golden template)
4. Tool results use Anthropic format: `"type": "tool_result"`, `"tool_use_id"`, `"content": string`
5. Return `agent_response` as string, not dict
6. Add try/except at top level returning error string

**Agents to update:**
- [ ] `git_agent.py` — Mr. Brandson
- [ ] `build_agent.py` — M. Jenkins
- [ ] `deploy_agent.py` — Madame Spinnaker
- [ ] `terraform_agent.py` — M. Terraform Inspector
- [ ] `docs_agent.py` — Secretary Confluence
- [ ] `general_agent.py` — Inspector Clouseau
- [x] `jira_agent.py` — Comptroller Jira ✅ DONE

### Stream C: Improve Prompts
**Files:** `carson_agents/agent_prompts.py`, `carson_agents/prompts.py`
**Goal:** Better routing, safety rules, consistent output format.

1. **CARSON_SYSTEM_PROMPT (Router):** Replace with the improved version from Section 4.2 of CARSON_FULL_REVIEW_v2.md (already written — just copy it in)
2. **Per-agent prompts:** Add safety rules section and output format section (templates in Section 4.3 of the review doc)
3. Add `Inspector Clouseau` to routing table if missing

### Stream D: Workflow & State Cleanup
**Files:** `carson_agents/workflow.py`, `carson_agents/agent_state.py`, `carson_service.py`

1. Remove `agent_result` from `CarsonState` if it still exists — only `agent_response` (string)
2. Clean up `initial_state` in `workflow.py` — remove deprecated fields
3. Add AWS token expiry detection in `carson_service.py`:
```python
if "InvalidClientTokenId" in str(e) or "ExpiredTokenException" in str(e) or "Expecting value" in str(e):
    print("\033[91mError: AWS token expired. Restart Carson.\033[0m")
```
4. Add conversation memory (deque-based, maxlen=10) in `carson_service.py`
5. Add retry logic for Bedrock throttling (exponential backoff, max 3 retries)

### Stream E: Dead Code & File Cleanup
**Files:** Various

1. **Delete or archive:** `carson_agents/llm/bedrock_client.py` — it's dead code, the real one is `carson_agents/bedrock_client.py`
2. Move test files to `tests/` directory
3. Move docs to `docs/` directory
4. Create `.env.example` with required env vars
5. Consolidate `*.ps1` scripts into single `carson_service.ps1`

### Stream F: Confirmation Node (New Feature)
**Files:** `agent_state.py`, `workflow.py`, new `confirmation_node.py`

1. Add `confirmation_required: Optional[str]` and `confirmed: Optional[bool]` to `CarsonState`
2. Create `confirmation_node.py` that checks if agent set `confirmation_required`
3. Add workflow branch: agent → confirmation_node → (if confirmed) → execute → synthesizer
4. Write operations (create, update, delete, transition) MUST set `confirmation_required`

---

## 5. Integration: .github Carson ↔ LangGraph

**Current state:** The `.github` Carson (simple single-agent) and the LangGraph Carson (multi-agent) are separate.

**Goal:** The `.github` version should be able to dispatch to the LangGraph system.

**Recommended approach — HTTP Gateway:**
```
.github Carson (simple)
  → POST http://localhost:8765/ask {"request": "..."}
  → LangGraph Carson processes with multi-agent routing
  → Returns {"final_response": "...", "agent": "...", "tool_results": [...]}
  → .github Carson displays result
```

**No synthesizer needed between them** — the LangGraph system already has its own response_synthesizer that produces `final_response`. The `.github Carson just needs to:
1. Forward the user request to the LangGraph endpoint
2. Display the `final_response` from the result
3. Handle errors (token expired, service down, etc.)

**If you want the .github Carson to also work standalone** (without LangGraph running), add a fallback:
```python
try:
    response = requests.post("http://localhost:8765/ask", json={"request": query}, timeout=30)
    return response.json()["final_response"]
except (requests.ConnectionError, requests.Timeout):
    # Fallback to direct Bedrock call (single-agent mode)
    return direct_bedrock_call(query)
```

---

## 6. Execution Order & Parallelization

```
Phase 1 (Parallel):
  ├─ Stream A: bedrock_client.py refactor
  ├─ Stream C: Prompt improvements
  └─ Stream E: Dead code cleanup

Phase 2 (After Stream A):
  └─ Stream B: Update all 6 remaining agents (can be parallelized per-agent)

Phase 3 (After Stream B):
  ├─ Stream D: Workflow & state cleanup
  └─ Stream F: Confirmation node

Phase 4:
  └─ Integration testing with Jira (get_sprints flow)
```

**Estimated token budget:** ~50K tokens for Streams A+C+E, ~80K for Stream B (all agents), ~30K for D+F.

---

## 7. Verification Checklist

After all changes:

- [ ] `grep -r "boto3" --include="*.py" . | grep -v test_ | grep -v __pycache__` → 0 results
- [ ] `grep -r "toolSpec" --include="*.py" carson_agents/agents/` → 0 results (except backward-compat checks)
- [ ] `grep -r "agent_result" --include="*.py" carson_agents/` → 0 results
- [ ] `grep -r "inputSchema" --include="*.py" carson_agents/agents/` → 0 results (use `input_schema`)
- [ ] Every agent returns `agent_response` as string
- [ ] `python carson_service.py` starts without import errors
- [ ] Test query: "Show me the Jiras from actual sprint" → routes to Jira agent, calls get_sprints

---

## 8. Files Reference (Quick Index)

| File | Purpose | Needs Changes |
|------|---------|---------------|
| `carson_agents/bedrock_client.py` | CDAO Bedrock wrapper (PRIMARY) | Stream A |
| `carson_agents/agents/jira_agent.py` | Jira agent — GOLDEN TEMPLATE | ✅ Done |
| `carson_agents/agents/git_agent.py` | Git/Bitbucket agent | Stream B |
| `carson_agents/agents/build_agent.py` | Jenkins CI agent | Stream B |
| `carson_agents/agents/deploy_agent.py` | Spinnaker deploy agent | Stream B |
| `carson_agents/agents/docs_agent.py` | Confluence docs agent | Stream B |
| `carson_agents/agents/terraform_agent.py` | Terraform/AWS agent | Stream B |
| `carson_agents/agents/general_agent.py` | General knowledge agent | Stream B |
| `carson_agents/agent_prompts.py` | All system prompts | Stream C |
| `carson_agents/prompts.py` | Per-agent prompts | Stream C |
| `carson_agents/agent_state.py` | CarsonState TypedDict | Stream D/F |
| `carson_agents/workflow.py` | LangGraph workflow definition | Stream D/F |
| `carson_service.py` | Flask HTTP service | Stream D |
| `carson_agents/llm/bedrock_client.py` | DEAD CODE — delete | Stream E |
| `carson_agents/router_node.py` | Intent detection & routing | Stream C (if prompt changes) |
| `carson_agents/inspector_node.py` | Quality review node | Review only |

---

*Generated 2026-03-30 by Claude (session with Martín)*
*For questions: garciatejedaml@gmail.com*
