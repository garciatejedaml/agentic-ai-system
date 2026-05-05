# Carson · canonical patterns

This is the **single source of truth** for how recurring tasks are
done in the Carson codebase. Every agent reads this before doing any
of the operations below. The premise: **we have working
implementations. Reuse them.** Reinventing is a finding, not a
feature.

If a pattern below doesn't fit your case exactly, **ask the human
before deviating**. Do not silently invent a one-off.

---

## §1. ChromaDB ingestion

### Where the canonical implementation lives

Search for the existing ingestion entry point:

```bash
grep -rln "chromadb\.PersistentClient\|chromadb\.Client" \
     --include="*.py" --exclude-dir=.venv --exclude-dir=.git . | head
```

The expected location is `carson_kb/ingest.py` (or a sibling under
`carson_data/` / `agents/`). The function signature follows:

```python
def ingest(
    source_path: str,
    collection: str,
    chunker: Chunker = AstChunker(),
    reranker: Reranker | None = LlmReranker(),
    embedder: Embedder = BedrockEmbedder(),
    metadata: dict | None = None,
) -> IngestResult:
    """Read source_path → chunk → embed → upsert into ChromaDB."""
```

### The pattern — what an agent does

When the human asks me to "embed this doc" or "add X to the knowledge
base", I:

1. **Locate the existing entry point** with the grep above. If found,
   I use it. End of decision.
2. **Identify the target collection** by asking the human or
   inferring from `carson_data/project_profiles/*.json`.
3. **Call the existing function** with appropriate args. I do not
   wrap it in my own helper.
4. **Verify the upsert** with the canonical query function (often
   `carson_kb/query.py::similarity_search`).

### Anti-patterns I avoid

| anti-pattern                                                    | what I do instead                              |
|-----------------------------------------------------------------|------------------------------------------------|
| Writing a new `chromadb.PersistentClient(...)` call            | Use the existing one in `carson_kb/`           |
| Picking a different chunker (e.g., naive `text.split('\n\n')`) | Use the project's `AstChunker` / `MdChunker`   |
| Choosing a different embedder model                            | Use the configured `BedrockEmbedder` model     |
| Writing my own collection naming convention                     | Read `project_profiles/*.json` for the names   |
| Creating a new collection without registering it               | Register via `kb_registry.register_collection` |

### When the human says "embed something new"

My response template:

```
I'll use the existing ingestion path:
  - entry point: carson_kb/ingest.py::ingest
  - chunker:     AstChunker (default) — fits if source is code
  - embedder:    BedrockEmbedder · titan-embed-text-v2
  - target collection: <ask human>
  - source path: <ask human>

Confirm collection + path, and I'll run.
```

I do NOT propose writing a new ingestion script. If the human
explicitly asks for one (e.g., "I want a new pipeline that handles
PDFs differently"), I treat that as a new pattern proposal and
follow §6 below.

---

## §2. Creating a new agent

### Where the base lives

Search for the agent base class:

```bash
grep -rn "class .*Agent.*BaseAgent\|class .*Agent.*Strands" \
     --include="*.py" agents/ langgraph-system/ | head
```

After the strands migration, the expected pattern uses Strands'
`Agent` directly, with a thin Carson wrapper. The canonical agent
file structure:

```python
# agents/<capability>_agent.py

from strands import Agent, tool
from carson_dashboard.stream import bus
from .base import CarsonAgentMixin, load_base_system  # §15 of GUARDRAILS

BASE_SYSTEM = load_base_system()  # AGENT_BEHAVIOR_GUARDRAILS.md

CAPABILITY_SYSTEM = """\
You are the {capability} agent. <role description>.

<scope and boundaries>

<HITL trigger conditions>
"""


@tool
def primary_action(arg: str) -> dict:
    """One-line description shown to the model. <when to use it>."""
    # implementation
    return {"ok": True, "result": ...}


@tool
def secondary_action(arg: int) -> dict:
    """One-line description. <when to use it>."""
    return {"ok": True, "result": ...}


class CapabilityAgent(CarsonAgentMixin, Agent):
    name = "{capability} agent"
    role = "<one-line role>"
    color = "#XXXXXX"   # for the dashboard avatar
    track  = "<coder | athena | git | ...>"

    def __init__(self, model_provider, deterministic: bool = False):
        super().__init__(
            model=model_provider,
            system_prompt=BASE_SYSTEM + "\n\n" + CAPABILITY_SYSTEM,
            tools=[primary_action, secondary_action],
            deterministic=deterministic,
        )
```

### The pattern — what an agent does

When the human asks me to "create a new agent for X":

1. **Search for an existing close match**. If `code agent` already
   exists and the human wants something 80% like it, I propose
   *extending* that agent, not creating a new one.
2. **If a new agent is justified**, I follow the file template
   above exactly — same imports, same `BASE_SYSTEM` load, same
   class structure, same `name`/`role`/`color`/`track` fields.
3. **I register it** via the canonical registry (§4 below).
4. **I add at least one test** in `tests/agents/test_<capability>_agent.py`.
5. **I propose a name following §13 of the guardrails** —
   `{capability} agent` form, no playful aliases.

### Anti-patterns I avoid

| anti-pattern                                                    | what I do instead                              |
|-----------------------------------------------------------------|------------------------------------------------|
| Subclassing my own custom `Agent` parent                       | Use Strands' `Agent` directly                  |
| Inlining the BASE_SYSTEM (copying §1-§15 of guardrails)        | Load via `load_base_system()`                  |
| Picking a model ID inside the agent file                        | Take `model_provider` as a constructor arg     |
| Picking the agent name from mythology / characters              | Use `{capability} agent` per §13               |
| Skipping the registry                                          | Register via `langgraph_registry.register`     |
| Writing tools without `@tool` decorator                        | Always use `@tool`; untyped args are forbidden |

### When the human says "I need a new agent"

My response template:

```
Before I create a new agent, two checks:

1. Existing close match — I see `code agent` already does ~70% of
   what you described. Want me to extend it instead, or is the new
   capability distinct enough to warrant its own agent?

2. If new — I'll follow the canonical template:
   - file:   agents/{capability}_agent.py
   - class:  {Capability}Agent
   - name:   "{capability} agent"  (per §13 guardrails)
   - tools:  <list — confirm with you>
   - model:  injected by the registry
   - tests:  one happy-path + one error-path

Confirm extend vs new, and the capability name.
```

---

## §3. Creating a new MCP tool / server

### Where the patterns live

```bash
ls mcp-servers/                   # one folder per server
cat mcp-servers/<example>/pyproject.toml   # the canonical pyproject
cat mcp-servers/<example>/server.py        # the canonical entrypoint
```

The expected MCP server structure:

```
mcp-servers/<service>-mcp/
├── pyproject.toml
├── README.md
├── <service>_mcp/
│   ├── __init__.py
│   ├── server.py        # entrypoint, registers tools
│   ├── tools.py         # @tool definitions, typed args
│   ├── auth.py          # auth scopes, token loading
│   └── client.py        # HTTP/SDK wrapper to <service>
└── tests/
    ├── test_tools.py
    └── test_auth.py
```

A typical `tools.py`:

```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

mcp = FastMCP("<service>")


class CreateIssueArgs(BaseModel):
    project: str
    summary: str
    type: str = "Story"
    priority: str = "Medium"


@mcp.tool()
def create_issue(args: CreateIssueArgs) -> dict:
    """Create a Jira issue. Use when the user explicitly asks to
    open a ticket. Returns {key, url}."""
    return _client.create_issue(**args.dict())


@mcp.tool()
def search_issues(jql: str, limit: int = 50) -> list[dict]:
    """Search Jira via JQL. Returns a list of {key, summary, status}."""
    return _client.search(jql, limit=limit)
```

### The pattern — what an agent does

When the human asks me to "add an MCP tool for X":

1. **Check if the service already has an MCP server** (`ls
   mcp-servers/`). If yes, I extend that server — same file, new
   `@mcp.tool()`. I do not create a parallel server.
2. **If a new server is justified**, I scaffold using the structure
   above. Pyproject, README, tests folder. No exceptions.
3. **Every tool has typed args via pydantic models**. Untyped
   `**kwargs` is forbidden.
4. **Every tool has a docstring with: what, when to use, returns**.
   The model uses these to decide.
5. **Auth lives in `auth.py`**, not in `tools.py`. Tools call
   `_client` which handles auth internally.
6. **Server is registered** with the langgraph orchestrator (§4).

### Anti-patterns I avoid

| anti-pattern                                                | what I do instead                              |
|-------------------------------------------------------------|------------------------------------------------|
| Creating a new server when one already exists for that service | Extend the existing server                |
| `@mcp.tool() def do_stuff(**kwargs):`                       | Pydantic model for args                        |
| Hardcoding the service URL                                   | Read from `MCP_<SERVICE>_URL` env / config     |
| Storing API tokens in source                                | Use `auth.py` reading from secret manager      |
| Skipping the test folder                                     | At least one happy-path + one auth-error test  |
| Tool docstrings like "calls the api"                        | "Create a Jira issue. Use when ... Returns ..." |

### When the human says "add a Jira tool"

My response template:

```
I see we already have `mcp-servers/jira-mcp/`. I'll extend it
rather than create a new server.

Proposed addition to mcp-servers/jira-mcp/jira_mcp/tools.py:

  @mcp.tool()
  def transition_issue(args: TransitionIssueArgs) -> dict:
      """Transition a Jira issue between workflow states.
      Use when the user explicitly asks to move a ticket
      (e.g., 'mark CARSN-123 as done'). Returns the new status."""
      ...

Need from you:
  - Should this hit the existing _client (yes/no)?
  - What scopes does the auth token need?
  - Any specific transition names to validate against?

Confirm and I'll add it + a test.
```

---

## §4. Registering with the langgraph orchestrator

### Where the registry lives

```bash
grep -rln "register_agent\|register_tool\|AgentRegistry\|langgraph_registry" \
     --include="*.py" --exclude-dir=.venv .
```

Expected location: `langgraph-system/registry.py` (or
`carson_dashboard/agent_rooms.py` for room-level registration).

The canonical registration flow:

```python
# langgraph-system/registry.py

from typing import Type
from strands import Agent
from .graph_builder import build_graph

_AGENTS: dict[str, Type[Agent]] = {}
_MCP_SERVERS: dict[str, str] = {}


def register_agent(name: str, agent_cls: Type[Agent]) -> None:
    """Register an agent class. Called at startup from each
    agents/<file>_agent.py module's __init__."""
    if name in _AGENTS:
        raise ValueError(f"agent {name} already registered")
    _AGENTS[name] = agent_cls


def register_mcp_server(name: str, url: str) -> None:
    """Register an MCP server URL. Called at startup."""
    if name in _MCP_SERVERS:
        raise ValueError(f"mcp server {name} already registered")
    _MCP_SERVERS[name] = url


def build_orchestrator(model_provider, deterministic: bool = False):
    """Build the langgraph orchestrator wiring every registered
    agent into the graph. Idempotent."""
    return build_graph(
        agents={name: cls(model_provider, deterministic=deterministic)
                for name, cls in _AGENTS.items()},
        mcp_servers=_MCP_SERVERS,
    )
```

### The pattern — what an agent does

When I create a new agent or MCP server, I **add the registration
call** in the appropriate place:

For agents — at the bottom of the agent file:

```python
# agents/code_agent.py
# (... class definition above ...)

from langgraph_system.registry import register_agent
register_agent("code agent", CodeAgent)
```

For MCP servers — at the bottom of `server.py`:

```python
from langgraph_system.registry import register_mcp_server
register_mcp_server(
    "jira",
    os.environ.get("MCP_JIRA_URL", "http://localhost:8081"),
)
```

For auto-discovery — the langgraph startup imports every module
in `agents/` and `mcp-servers/<*>/`, which triggers the
`register_*` calls. **No manual registration list anywhere.**

### Anti-patterns I avoid

| anti-pattern                                                | what I do instead                              |
|-------------------------------------------------------------|------------------------------------------------|
| Maintaining a separate `KNOWN_AGENTS = [...]` list           | Auto-register at module load                   |
| Calling `register_agent` from a config YAML                  | Code, not YAML, registers                       |
| Creating an agent and forgetting the `register_agent` line   | Linter check — see test below                   |
| Two agents registered with the same name                     | The registry raises; pick distinct names       |

### Verification — the registration test

There must be a test that asserts every file in `agents/` registers
exactly one agent:

```python
# tests/test_registry.py

import pkgutil, importlib
import agents
from langgraph_system.registry import _AGENTS

def test_all_agents_registered():
    """Every agents/*.py file must register exactly one agent."""
    files = [m.name for m in pkgutil.iter_modules(agents.__path__)
             if m.name.endswith("_agent")]
    for f in files:
        importlib.import_module(f"agents.{f}")
    assert len(_AGENTS) == len(files), \
        f"agent count mismatch: {len(_AGENTS)} registered vs {len(files)} files"
```

If this test fails, I have either:
- An agent file that didn't call `register_agent` (fix: add the call)
- Two agents with the same name (fix: pick distinct names per §13)

---

## §5. Writing a tool the human will actually want to call

A tool function isn't just a Python function with a decorator. The
model decides when to use it based on:
1. The function name
2. The docstring's first sentence
3. The argument types and names

### The discipline

| field            | how to write it                                            |
|------------------|------------------------------------------------------------|
| Function name    | verb + noun. `create_issue`, not `issue` or `do_create`    |
| First docstring sentence | What the tool does, in present tense, in < 12 words |
| Subsequent docstring     | When to use it. When NOT to use it. What it returns. |
| Argument names   | full words, not abbreviations. `repository`, not `r`       |
| Argument types   | Pydantic models for > 1 arg. Single primitive args OK.     |

### Example

```python
@tool
def create_issue(args: CreateIssueArgs) -> dict:
    """Create a Jira issue.

    Use when the user explicitly asks to open a ticket. Do NOT use
    for searching or transitioning existing issues — those have
    their own tools (`search_issues`, `transition_issue`).

    Returns {"key": str, "url": str}.
    """
    return _client.create_issue(**args.dict())
```

Note what's in the docstring: *what*, *when to use*, *when NOT to
use*, *return shape*. All four. In that order.

---

## §6. Proposing a new pattern

If a task doesn't fit any pattern above, I do not silently invent
one. I propose it explicitly:

```
I'm about to introduce a new pattern in the codebase.

Pattern name:        <one-line title>
Existing alternatives: <why none fit>
Proposed location:   <file path>
Proposed shape:      <code excerpt>
Justification:       <one paragraph>

Once approved, I'll add a §X to CARSON_PATTERNS.md so future agents
follow it instead of reinventing.

Approve / suggest changes?
```

Approved patterns get a PR adding a section to this document with:
- Where the canonical impl lives
- The pattern (code template)
- Anti-patterns to avoid
- The agent's response template

---

## §8. LLM-based routing (no keywords)

### Why

Heuristic keyword routing does not scale. Every new agent forces
us to add keywords; ambiguous tokens misroute; "endpoint" matches
both `code agent` and `infra agent` depending on context the
keyword can't see.

The canonical router uses a **small fast LLM** (Haiku 4.5 or its
successor) given a structured prompt that includes the agent
catalog and returns a strict JSON classification.

### Where the canonical impl lives

```bash
grep -rn "classify\|routing\|route_to_agent" \
     --include="*.py" agents/ langgraph-system/ | head
```

Expected location: `langgraph-system/router.py` (or
`langgraph-system/router_node.py`).

### The pattern

```python
# langgraph-system/router.py

from strands import Agent, tool
from .registry import _AGENTS  # auto-discovered agents
from .agent_catalog import format_agent_catalog


ROUTER_SYSTEM = """\
You are the Carson router. Your only job: read a user request and
output JSON saying which agent should handle it.

Output schema (strict):
{
  "agent": "<exact agent name from the catalog>",
  "confidence": 0.0..1.0,
  "track":     "<the agent's track>",
  "rationale": "<one sentence — why this agent>",
  "fallback":  "<second-best agent name, or null>"
}

Rules:
- The agent name MUST be one from the catalog. No invention.
- If the request is ambiguous (confidence < 0.7), return the
  best guess + a non-null fallback so the orchestrator can
  ask the human to disambiguate.
- Do NOT use surface keywords. Read for intent.
"""


def build_router(model_provider) -> Agent:
    catalog = format_agent_catalog(_AGENTS)
    return Agent(
        model=model_provider,        # Haiku 4.5 or equivalent
        system_prompt=ROUTER_SYSTEM + "\n\n" + catalog,
        tools=[],                     # router has no tools — it just classifies
        deterministic=True,           # routing is a graph, not reactive
        max_tokens=200,
    )


def classify(request: dict, router_agent: Agent) -> dict:
    """request: {summary, description, labels, repo, ...}.
    Returns {agent, confidence, track, rationale, fallback}."""
    response = router_agent.run(format_request(request))
    return parse_classification(response)
```

### Anti-patterns I avoid

| anti-pattern                                                  | what I do instead                                       |
|---------------------------------------------------------------|---------------------------------------------------------|
| `if "deploy" in text: return "spinnaker agent"`               | Single LLM classify call                                |
| Heuristic-first with LLM fallback                             | LLM-first; heuristic is deprecated                      |
| Keyword lists per agent                                        | The agent catalog + descriptions are enough            |
| Routing through a static dict like `{"deploy": "spinnaker"}`  | Catalog → LLM → classification                          |
| Multiple competing routers (one per request type)              | One router. One model. Same catalog.                   |

### When the human says "the routing is wrong"

My response:

```
Two possibilities:

1. The catalog is incomplete or ambiguous — the LLM doesn't have
   enough description to pick correctly. Fix: improve the agent's
   `role` field in its registration.

2. The router's system prompt is too narrow / too broad — fix
   ROUTER_SYSTEM in langgraph-system/router.py.

Which case is it? I'll show you the rationale for the bad
classifications so we can tell.
```

**Never** my response: "let me add a keyword for that case".

### Migration: the heuristic router exists; how to remove it

The legacy `classifier.py` in `carson_dashboard/` uses heuristic
keywords. It must be **wrapped, deprecated, and eventually deleted**:

1. Wrap: have the heuristic call the LLM router and only fall back
   if the LLM is unavailable. Log every fallback.
2. Deprecate: emit a warning every time the heuristic resolves a
   classification.
3. Delete: once 30 days of logs show < 0.1% fallback rate.

---

## §9. The critic loop

### Why

The current loop pattern is "agent runs → tests pass/fail → retry
on fail". This is too dumb. A retry of a prompt that produced bad
code usually produces another bad version. The loop needs a
**critic** that scores the output and produces *direction*, not
just pass/fail.

### Where the canonical impl lives

```bash
grep -rln "critic\|scorer\|self_review\|grader" \
     --include="*.py" agents/ langgraph-system/ | head
```

Expected location: `langgraph-system/critic.py`.

### The pattern

The critic is its own agent. It runs **after** the primary agent
produces a candidate output. Its job:

1. Score the candidate on multiple dimensions.
2. If any dimension is below threshold, produce a **directive** —
   not just "fail", but "the test for X is missing; add it before
   retrying" or "the function is correct but doesn't match the
   existing repo style; here's what to change".
3. Send that directive back into the primary agent's next turn.

```python
# langgraph-system/critic.py

CRITIC_SYSTEM = """\
You are the Carson critic. You receive: (a) the original task,
(b) the primary agent's candidate output. You produce a JSON
verdict.

Schema (strict):
{
  "verdict":     "approve" | "request_changes" | "reject",
  "scores": {
    "correctness":    0.0..1.0,
    "style":          0.0..1.0,
    "completeness":   0.0..1.0,
    "tests":          0.0..1.0,
    "performance":    0.0..1.0,
    "scope_respect":  0.0..1.0   # did it stay in scope or did it sprawl
  },
  "directive": "<actionable next-step instruction, or empty>",
  "rationale": "<one paragraph — what the agent should know>"
}

Verdict rules:
- approve:          all scores >= 0.8
- request_changes:  one or two scores in [0.5, 0.8); directive
                    must be specific and actionable
- reject:           any score < 0.5 OR scope_respect < 0.7;
                    rationale must explain how to re-plan
"""


def build_critic(model_provider) -> Agent:
    return Agent(
        model=model_provider,        # Sonnet or equivalent
        system_prompt=CRITIC_SYSTEM,
        tools=[],
        deterministic=True,
        max_tokens=600,
    )
```

### Loop control

The orchestrator caps the loop at `MAX_LOOPS = 3` (configurable per
agent). On each iteration:

1. Primary agent runs → produces candidate.
2. Critic runs → produces verdict + directive.
3. If `verdict == approve` → done.
4. If `verdict == request_changes` AND `loop < MAX_LOOPS` →
   primary agent runs again with the directive prepended.
5. If `verdict == reject` OR `loop == MAX_LOOPS` → escalate to HITL.

The critical detail: **the directive is prepended to the next
turn, not the rationale.** Rationale is for the human; directive
is for the agent.

### Anti-patterns I avoid

| anti-pattern                                          | what I do instead                                    |
|-------------------------------------------------------|------------------------------------------------------|
| Retry the same prompt with `temperature` raised        | Feed the critic's directive back into the prompt    |
| Boolean pass/fail                                     | Multi-dimensional scoring with thresholds            |
| Critic that is also a tool of the primary agent       | Critic is a separate agent in the graph             |
| `MAX_LOOPS = 100` as a runtime guard                  | `MAX_LOOPS = 3`; hitting it means escalate to HITL   |
| Same model for primary and critic                     | Critic uses a different / larger model where useful  |

### When the human says "the loop just spins"

My response:

```
Likely diagnosis: the critic is verdicting "request_changes" with
a vague directive, and the primary agent can't act on it.

Two fixes:
1. Tighten the critic's directive (require concrete next-action
   instructions). I can show you the last 5 directives in the
   trace; you'll see they're too abstract.
2. Lower MAX_LOOPS to 2 — if it can't fix in 2 tries, escalate
   sooner.

Which one do you want me to apply first? The first is a critic
prompt fix; the second is a config change.
```

---

## §10. Autonomous agent variants

### What's missing today

Today's autonomous coders are `code agent` (general) and
`release agent` (CI/release). The user wants the same autonomous
treatment for two more domains:

- **`autonomous git agent`** — takes a Jira ticket asking for git
  operations (branch surgery, history rewrites, merge resolutions)
  and runs the same 9-phase swimlane.
- **`autonomous athena agent`** — takes a Jira ticket asking for
  knowledge-base operations (re-embed a corpus, migrate a
  collection, prune stale chunks) and runs end-to-end with HITL
  before any destructive op.

### The pattern

These are not separate from the existing agent registry — they're
**autonomous-mode** variants of `bitbucket agent` and the athena
knowledge agents.

The pattern is: every agent declares whether it supports autonomous
mode at registration time:

```python
class BitbucketAgent(CarsonAgentMixin, Agent):
    name = "bitbucket agent"
    role = "git operations on Bitbucket"
    track = "git"
    color = "#a78bfa"
    supports_autonomous = True       # NEW
    autonomous_phases = [             # NEW — defines the swimlane
        "intake", "plan", "branch", "diff", "test",
        "commit", "pr", "review", "merge",
    ]
```

The orchestrator's autonomous loop reads `autonomous_phases` and
runs exactly those phases. The router routes autonomous tickets
only to agents where `supports_autonomous=True`.

### Per-track phase templates

| track   | phases                                                                |
|---------|------------------------------------------------------------------------|
| coder   | clone, analyze, generate, test, commit, pr, review, build, deploy      |
| git     | intake, plan, branch, diff, test, commit, pr, review, merge            |
| athena  | intake, scan, snapshot, embed, validate, swap, prune, audit, archive   |
| infra   | intake, plan, validate, apply, drift, audit, rollback?, doc            |

Each track's phase list is canonical. Adding/renaming phases in a
track requires a PR + agent registry update. Don't ad-hoc.

### Anti-patterns I avoid

| anti-pattern                                                        | what I do instead                            |
|---------------------------------------------------------------------|----------------------------------------------|
| Subclassing the coder agent for git autonomous mode                 | Add `supports_autonomous=True` + `autonomous_phases` to the existing agent |
| Hardcoding phase names in the orchestrator                          | Read from the agent's `autonomous_phases` |
| Routing autonomous tickets to any agent regardless of mode support  | Filter to `supports_autonomous=True` agents |
| One swimlane shape for all tracks                                   | Per-track phase templates above             |

### When the human says "I want autonomous athena"

My response:

```
I'll extend the existing athena agents (bob, hydra, csb, pixie,
studio after the §13 rename) with the autonomous-mode flag and the
canonical athena phase list.

Specifically:
  - Add to each athena agent class:
      supports_autonomous = True
      autonomous_phases = ["intake", "scan", "snapshot", "embed",
                           "validate", "swap", "prune", "audit", "archive"]
  - Add a HITL gate at "swap" (the destructive op) and "prune"
  - Update the autonomous router to include the athena agents in
    its candidate pool when it sees Jira labels matching athena work

Confirm and I'll open one PR per athena agent (5 PRs total) so the
review is bounded.
```

---

## §7. Self-check before any pattern-eligible task

Before doing any task that resembles ingestion, agent creation,
MCP tool creation, or registration, I confirm out loud:

> "This is a §X-eligible task per CARSON_PATTERNS.md. I'll follow
> the canonical pattern at <path> and the response template
> there. If something doesn't fit, I'll stop and ask before
> deviating."

This sentence is not theater. It's a gate that catches the agent
about to invent a bespoke solution.
