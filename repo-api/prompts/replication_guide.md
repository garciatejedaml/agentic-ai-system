# Agentic AI System — Complete Replication Guide for Claude Code

> **Purpose**: This document contains everything Claude Code needs to replicate the
> Agentic AI System from scratch on a new machine or in a new environment.
> Read every section before writing any code. The architecture decisions are intentional.

---

## 1. What this system is

A **multi-agent financial analysis system** for Bond trading desks. It answers
natural language queries by orchestrating three data sources:

| Data source | Technology | What it has |
|-------------|------------|-------------|
| Historical RFQ data | KDB+/DuckDB + Parquet | 6 months of Bond trade requests (hit rates, spreads, notionals) |
| Live market data | AMPS pub/sub | Real-time positions, orders, market prices |
| Domain knowledge | RAG + ChromaDB | AMPS docs, bond market concepts, strategy definitions |

**Example queries the system handles:**
- "Which HY traders had the best hit rate last 6 months?"
- "What are current open orders on the IG desk?"
- "What is AMPS SOW and how does it differ from subscribe?"
- "Compare Goldman Sachs 6.75% spread history vs current live quote"

---

## 2. Architecture — read this before touching any code

### 2.1 Two-framework hybrid

The system deliberately uses **two agent frameworks** for different purposes:

```
┌──────────────────────────────────────────────────────────────────┐
│  LangGraph (deterministic control plane)                         │
│  Provides: graph structure, RAG pipeline, API server             │
│                                                                  │
│  START → intake → retrieve → strands → format → END             │
│                      │           │                               │
│                  ChromaDB     Strands                            │
│                  vector       orchestrator                       │
│                  search       (see below)                        │
└──────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Strands (non-deterministic data plane)                          │
│  Provides: agent reasoning, tool use, multi-agent coordination   │
│                                                                  │
│  Strands Orchestrator                                            │
│    ├─ keyword routing (no LLM call for routing decision)         │
│    │                                                             │
│    ├─ Financial pipeline (bond/trading/AMPS keywords detected)   │
│    │    Financial Orchestrator (claude-sonnet, agent-as-tool)    │
│    │      ├─ KDB Agent    (claude-haiku, MCP tools)              │
│    │      ├─ AMPS Agent   (claude-haiku, MCP tools)              │
│    │      └─ RAG tool     (direct ChromaDB call, no LLM)         │
│    │                                                             │
│    └─ General pipeline (all other queries)                       │
│         Researcher Agent (claude-haiku, MCP tools)              │
│         Synthesizer Agent (claude-haiku)                        │
└──────────────────────────────────────────────────────────────────┘
```

**Why two frameworks?**
- LangGraph provides a stable, observable graph (Langfuse can visualize it)
- Strands handles the unpredictable reasoning where the agent decides which tools to call
- The boundary is clean: LangGraph's `strands` node calls `run_strands_orchestrator()`

### 2.2 Agent-as-tool pattern

The Financial Orchestrator uses the **agent-as-tool** pattern: each specialist
is wrapped as a `@tool` function that instantiates its own Strands Agent:

```python
@tool
def query_kdb_history(query: str) -> str:
    from src.agents.kdb_agent import run_kdb_agent
    return run_kdb_agent(query)   # spawns a Haiku agent with KDB MCP tools

@tool
def query_amps_data(query: str) -> str:
    from src.agents.amps_agent import run_amps_agent
    return run_amps_agent(query)  # spawns a Haiku agent with AMPS MCP tools
```

The orchestrator (Sonnet) calls these tools. Each tool runs a full sub-agent with
its own LLM call, tool use loop, and result formatting.

### 2.3 MCP (Model Context Protocol) for all external integrations

All external tools use the **MCP standard** (Anthropic's open protocol):
- KDB tools → `src/mcp_server/kdb_mcp_server.py` (Python subprocess, stdio transport)
- AMPS tools → `src/mcp_server/amps_mcp_server.py` (Python subprocess, stdio transport)
- Brave Search → `@modelcontextprotocol/server-brave-search` (npm package)
- File read → `@modelcontextprotocol/server-filesystem` (npm package)
- URL fetch → `mcp-server-fetch` (uvx package)

**Why MCP?** Swappable — the Strands Agent doesn't know what tools it has until
they're passed in. In AWS, you can replace stdio with HTTP+SSE transport without
changing the agent code.

### 2.4 Tiered model strategy

```
claude-sonnet-4-6   → orchestrators (complex reasoning, cross-source synthesis)
claude-haiku-4-5    → sub-agents (tool-calling, result formatting)
```

This gives ~60-70% cost reduction vs all-Sonnet. Haiku is ~20x cheaper per token
and is perfectly adequate for "look at this tool result and format it nicely".

The model is selected via `get_strands_model()` vs `get_strands_fast_model()`
in `src/agents/model_factory.py`. The factory supports both local (Anthropic API
via LiteLLM) and AWS production (Bedrock, IAM auth, no API key).

### 2.5 Routing strategy

No LLM call is used for routing. Keyword matching:

```python
_FINANCIAL_KEYWORDS = {"bond", "rfq", "trader", "hy", "ig", "em", "spread",
                       "live", "amps", "kdb", "position", "order", ...}

if any(kw in query.lower() for kw in _FINANCIAL_KEYWORDS):
    → Financial Orchestrator (KDB + AMPS + RAG)
else:
    → General pipeline (Researcher + Synthesizer + web search)
```

**Why keyword routing?** An extra LLM routing call adds 500ms+ and cost. The
financial vs general distinction is clear enough for keywords. The Financial
Orchestrator itself decides which sub-tools to call (that's where LLM reasoning
is needed).

---

## 3. Project structure (every file explained)

```
agentic-ai-system/
├── main.py                          ← CLI entry point (python main.py "query")
├── Dockerfile                       ← Production container (ECS Fargate)
├── requirements.txt                 ← Python dependencies
├── .env                             ← Local secrets (never commit)
├── .env.example                     ← Template for .env
├── .gitignore                       ← Key exclusions: .env, amps/, kc.lic, .chroma_db
│
├── src/
│   ├── config.py                    ← All config from env vars (Config class)
│   ├── observability.py             ← Langfuse + Phoenix OTEL setup
│   ├── mcp_clients.py               ← MCP client factories + context managers
│   │
│   ├── api/
│   │   └── server.py                ← FastAPI OpenAI-compatible endpoint
│   │
│   ├── graph/
│   │   ├── state.py                 ← AgentState TypedDict
│   │   ├── nodes.py                 ← LangGraph node functions
│   │   └── workflow.py              ← Graph assembly + run_query()
│   │
│   ├── agents/
│   │   ├── model_factory.py         ← get_strands_model() / get_strands_fast_model()
│   │   ├── orchestrator.py          ← Strands orchestrator (keyword routing)
│   │   ├── financial_orchestrator.py← Financial specialist (KDB+AMPS+RAG tools)
│   │   ├── kdb_agent.py             ← KDB specialist (historical analytics)
│   │   ├── amps_agent.py            ← AMPS specialist (live data)
│   │   ├── researcher.py            ← General researcher (web search + docs)
│   │   ├── synthesizer.py           ← Synthesizer (formats final answer)
│   │   └── tools.py                 ← Shared Strands tools (RAG search, summarize)
│   │
│   ├── rag/
│   │   └── retriever.py             ← ChromaDB setup + get_retriever()
│   │
│   └── mcp_server/
│       ├── kdb_mcp_server.py        ← KDB MCP server (5 tools, DuckDB backend)
│       └── amps_mcp_server.py       ← AMPS MCP server (5 tools, HTTP admin + TCP)
│
├── scripts/
│   ├── generate_synthetic_rfq.py    ← Creates bond_rfq.parquet (synthetic data)
│   ├── ingest_docs.py               ← Ingest general docs to ChromaDB
│   ├── ingest_amps_docs.py          ← Ingest AMPS-specific docs to ChromaDB
│   ├── amps_publisher.py            ← AMPS live data simulator (seed + tick modes)
│   └── test_amps_realtime.py        ← Canary test: proves live data flows from AMPS SOW
│
├── data/
│   ├── kdb/bond_rfq.parquet         ← Synthetic Bond RFQ historical data
│   └── sample_docs/                 ← Text docs ingested into RAG
│
├── docker/
│   ├── entrypoint.sh                ← Container startup (ingest + uvicorn)
│   ├── amps/
│   │   ├── Dockerfile               ← AMPS server container (linux/amd64)
│   │   └── config.xml               ← AMPS server config (ports 8085, 9007)
│   └── kdb/
│       ├── Dockerfile               ← KDB+ server container
│       └── init.q                   ← KDB initialization script
│
├── docker-compose.amps.yml          ← Local AMPS server
├── docker-compose.kdb.yml           ← Local KDB+ server
├── docker-compose.observability.yml ← Langfuse + Phoenix + ClickHouse + Postgres
│
├── infra/                           ← Terraform (AWS)
│   ├── main.tf                      ← AWS provider + S3 backend (commented out, ready to activate)
│   ├── variables.tf                 ← Input variables with defaults
│   ├── locals.tf                    ← Computed values (name_prefix, Bedrock model IDs)
│   ├── outputs.tf                   ← ALB DNS, ECR URL, cluster name, etc.
│   ├── networking.tf                ← VPC, 3 subnet tiers, NAT Gateway, security groups
│   ├── vpc_endpoints.tf             ← VPC Endpoints: Bedrock, ECR×2, SQS, Secrets, CW, S3
│   ├── ecr.tf                       ← ECR repository + lifecycle policy
│   ├── iam.tf                       ← Task role (Bedrock + SQS + DynamoDB) + Execution role
│   ├── data.tf                      ← Aurora pgvector, DynamoDB registry, SQS + DLQ, Secrets Manager
│   ├── ecs.tf                       ← ECS cluster, task definition, Fargate service
│   ├── alb.tf                       ← ALB, target group, HTTP listener
│   ├── autoscaling.tf               ← Auto-scaling by CPU/memory (1–4 tasks)
│   └── terraform.tfvars.example     ← Variable template — copy to terraform.tfvars
│
└── tests/
    ├── test_graph.py                ← LangGraph node tests
    └── test_rag.py                  ← RAG retrieval tests
```

---

## 4. Build instructions — step by step

### 4.1 Prerequisites

```bash
# Python 3.11 (3.14 has compatibility issues with some packages)
python --version   # should be 3.11.x

# Node.js 18+ (for MCP npm servers)
node --version     # should be 18+

# uv (for mcp-server-fetch via uvx)
pip install uv

# Docker Desktop (for AMPS, KDB, observability containers)
docker --version
```

### 4.2 Setup

```bash
git clone <repo>
cd agentic-ai-system

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Install AMPS Python client (not on PyPI, local zip)
pip install amps/client/amps-python-client-*.zip
```

### 4.3 Environment variables

Copy `.env.example` to `.env` and fill in:

```bash
# Required for local dev
ANTHROPIC_API_KEY=sk-ant-...

# Models (tiered strategy)
LLM_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-sonnet-4-6      # orchestrators
ANTHROPIC_FAST_MODEL=claude-haiku-4-5  # sub-agents

# Optional: enable KDB historical data
KDB_ENABLED=true
KDB_MODE=poc   # uses DuckDB + parquet, no license needed

# Optional: enable AMPS live data (requires AMPS Docker container)
AMPS_ENABLED=true
AMPS_HOST=localhost
AMPS_PORT=9007

# Optional: web search
BRAVE_API_KEY=BSA_...

# Optional: observability (requires docker-compose.observability.yml)
OBSERVABILITY_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

### 4.4 Generate synthetic KDB data

```bash
python scripts/generate_synthetic_rfq.py
# Creates: data/kdb/bond_rfq.parquet (~50k Bond RFQ records)
```

The parquet contains:
- `rfq_id`, `timestamp`, `trader_id`, `desk` (HY/IG/EM/RATES)
- `isin`, `bond_name`, `issuer`, `coupon`
- `notional_usd`, `side` (buy/sell), `spread_bps`, `price`
- `hit` (boolean: did trader win the RFQ?), `hit_rate` (rolling 30-day)

Traders: T_HY_001..T_HY_005 (HY desk), T_IG_001..T_IG_003, T_EM_001..T_EM_002, T_RATES_001..T_RATES_002

Bonds: 12 ISINs (5 HY, 3 IG, 2 EM, 2 RATES) with realistic prices, spreads, coupons.

### 4.5 Ingest docs to RAG

```bash
python scripts/ingest_docs.py       # general docs (LangGraph, Strands intros)
python scripts/ingest_amps_docs.py  # AMPS-specific docs (concepts, tools, config)
```

ChromaDB persists to `.chroma_db/` locally or `/data/chroma_db` in Docker.

### 4.6 Run the AMPS real-time canary test

After starting AMPS and seeding data, verify the live data flow end-to-end:

```bash
python scripts/test_amps_realtime.py          # concise output
python scripts/test_amps_realtime.py --verbose # shows full agent responses
```

The test publishes a position with `PnL = 7,777,777.77` (a value impossible in real
financial data), queries the AMPS agent, and asserts that exact value appears in the
response — proving the system reads from AMPS SOW and not from KDB or any cache.
It then updates the record to `PnL = 9,999,999.99` and re-queries to confirm live
SOW updates are reflected. Exit code 0 = all pass, exit code 1 = failure.

### 4.7 Start optional services

```bash
# AMPS pub/sub server (requires docker/amps/AMPS.tar — download from crankuptheamps.com/evaluate)
docker compose -f docker-compose.amps.yml up -d

# Seed AMPS with synthetic live data
python -u scripts/amps_publisher.py --mode seed
# Or: continuous live simulation
python -u scripts/amps_publisher.py --mode both --interval 2

# Observability: Langfuse (localhost:3000) + Phoenix (localhost:6006)
docker compose -f docker-compose.observability.yml up -d
```

### 4.7 Run

```bash
# CLI (single query)
python main.py "Which HY traders had the best hit rate last 6 months?"

# API server (OpenAI-compatible)
uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Who are the top HY traders?"}]}'
```

---

## 5. Key implementation details

### 5.1 KDB MCP server tools

File: `src/mcp_server/kdb_mcp_server.py`

| Tool | Purpose |
|------|---------|
| `kdb_query_rfq` | Query Bond RFQ records with optional filters (desk, trader, date range, isin) |
| `kdb_trader_stats` | Aggregate stats per trader: avg hit_rate, total notional, avg spread |
| `kdb_desk_summary` | Desk-level stats: compare HY vs IG vs EM vs RATES |
| `kdb_time_series` | Hit rate or spread over time (daily/weekly buckets) |
| `kdb_top_traders` | Rank traders by hit_rate, notional, or spread discipline |

All tools use DuckDB in `poc` mode — no KDB+ license required. In `server` mode,
PyKX connects to a real KDB+ instance.

The server starts with `mcp.run(transport="stdio")` and is launched as a subprocess
by `src/mcp_clients.py:_kdb_client()`.

### 5.2 AMPS MCP server tools

File: `src/mcp_server/amps_mcp_server.py`

| Tool | Purpose |
|------|---------|
| `amps_server_info` | GET http://localhost:8085/amps.json — server status, uptime, clients |
| `amps_list_topics` | GET http://localhost:8085/topics.json — all topics with message counts |
| `amps_sow_query` | State-of-World: current snapshot of all records in a topic (with optional filter) |
| `amps_subscribe` | Capture N recent streaming messages from a topic |
| `amps_publish` | Publish a JSON message to a topic |

AMPS SOW filter syntax: `/field = 'value'` (e.g. `/desk = 'HY'`).
`amps_sow_query` is preferred over `amps_subscribe` for "current state" questions.

AMPS topics:
- `positions` — keyed by `/id` (`{trader_id}_{isin}`), stores current trader positions
- `orders` — keyed by `/order_id`, stores live bond orders
- `market-data` — keyed by `/symbol` (ISIN), stores live bond prices

### 5.3 RAG setup

File: `src/rag/retriever.py`

- Embedding model: `all-MiniLM-L6-v2` (local, runs offline, 384-dim vectors)
- Vector store: ChromaDB (local SQLite, no server needed)
- Retrieval: top-4 chunks by cosine similarity
- Used in: LangGraph `retrieve` node + `search_knowledge_base` Strands tool

ChromaDB has 18+ chunks covering:
- AMPS concepts (SOW, subscribe, pub/sub, topics, filters)
- AMPS MCP tool descriptions
- AMPS server configuration
- Bond market concepts (spread_bps, hit_rate, RFQ, desks)
- KDB MCP tool descriptions
- LangGraph and Strands framework intros

### 5.4 Observability

File: `src/observability.py`

Dual tracing via a single OTEL exporter:
- **Langfuse** (localhost:3000): LangGraph graph view, prompt cost tracking, session timelines
- **Phoenix/Arize** (localhost:6006): RAG chunk analysis, span explorer

Enabled with `OBSERVABILITY_ENABLED=true`. The Langfuse callback is injected into
`graph.invoke(config={"callbacks": [langfuse_cb]})`.

Containers: `docker-compose.observability.yml` starts Langfuse, Phoenix, ClickHouse, Postgres.

### 5.5 The AMPS publisher simulator

File: `scripts/amps_publisher.py`

Publishes synthetic live data to AMPS SOW topics. Uses the same 12 ISINs and
12 traders as the KDB dataset — this allows the Financial Orchestrator to
correlate historical (KDB) vs live (AMPS) data.

```bash
python scripts/amps_publisher.py --mode seed     # initial snapshot
python scripts/amps_publisher.py --mode tick     # only publish updates
python scripts/amps_publisher.py --mode both     # seed then loop (default)
python scripts/amps_publisher.py --interval 1    # 1 second between ticks
```

Key implementation: `client.publish(topic_string, json_string)` — the AMPS Python
client API takes two string arguments (not a Message object).

---

## 6. AWS deployment — Phase 1 (single service)

### Architecture

```
ALB → ECS Fargate (agentic-ai-api) → Amazon Bedrock (Claude via IAM)
                 ↓
         MCP servers as subprocesses (stdio, same container)
                 ↓
         ChromaDB (in-process) or EFS mount
```

### Key config changes for AWS

In `src/config.py` (already done, driven by env vars):
```python
LLM_PROVIDER=bedrock           # use BedrockModel instead of LiteLLMModel
BEDROCK_MODEL=us.anthropic.claude-sonnet-4-6-20251101-v1:0
```

In `src/agents/model_factory.py` (already done):
```python
def get_strands_model():
    if config.is_local():
        return LiteLLMModel(...)    # Anthropic API
    else:
        return BedrockModel(        # IAM auth, no API key
            model_id=config.BEDROCK_MODEL,
            region_name=config.AWS_REGION,
        )
```

IAM task role needs: `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`.

### Terraform deployment

See `infra/README.md` for full steps. Summary:

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

---

## 7. AWS deployment — Phase 2 (multi-tenant agent platform)

This is the target architecture for supporting multiple teams/agents.

### Concept

```
                      ┌──────────────────────────────┐
                      │  API Gateway / ALB            │
                      │  POST /v1/chat/completions    │
                      └──────────────┬───────────────┘
                                     │
                      ┌──────────────▼───────────────┐
                      │  LangGraph API (ECS service) │
                      │  Always-on, 1-4 tasks        │
                      └──────────────┬───────────────┘
                                     │ submit job
                      ┌──────────────▼───────────────┐
                      │  SQS Job Queue               │
                      └──────────────┬───────────────┘
                                     │ consume
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
┌─────────────▼──────────┐  ┌───────▼────────┐  ┌──────────▼──────────┐
│  Financial Orchestrator│  │  KDB Agent     │  │  AMPS Agent         │
│  ECS Fargate task      │  │  ECS Fargate   │  │  ECS Fargate        │
│  Scale 0→N on SQS depth│  │  task          │  │  task               │
└────────────────────────┘  └───────┬────────┘  └──────────┬──────────┘
                                    │ MCP HTTP               │ MCP HTTP
                            ┌───────▼────────┐  ┌──────────▼──────────┐
                            │  kdb-mcp ECS   │  │  amps-mcp ECS       │
                            │  service :5002 │  │  service :5001      │
                            └────────────────┘  └─────────────────────┘
```

### Required code changes for Phase 2

1. **MCP transport**: Change stdio → HTTP+SSE
   In `src/mcp_clients.py`, replace `stdio_client(StdioServerParameters(...))` with:
   ```python
   from mcp import sse_client
   MCPClient(lambda: sse_client(f"http://amps-mcp:5001/sse"))
   ```

2. **Agent as separate container**: Each agent becomes its own Fargate task
   that polls SQS for jobs and returns results to a response queue (or DynamoDB).

3. **Agent Registry in DynamoDB**: The orchestrator queries the registry to
   discover which agents are available (already in DataStack):
   ```python
   # Agent registration record:
   {
     "agent_id": "financial-orchestrator",
     "desk_names": ["HY", "IG", "EM", "RATES"],
     "keywords": ["bond", "rfq", "trader", ...],
     "task_def_arn": "arn:aws:ecs:...",
     "mcp_endpoints": {"kdb": "http://kdb-mcp:5002", "amps": "http://amps-mcp:5001"},
     "model": "us.anthropic.claude-sonnet-4-6-...",
   }
   ```

4. **New team onboarding**: A team writes a new ECS task definition + pushes their
   agent image, then registers an entry in the DynamoDB table. The orchestrator
   picks it up dynamically.

---

## 8. Technology choices and rationale

| Choice | Why |
|--------|-----|
| **LangGraph** for graph | Provides deterministic flow, observability hooks (Langfuse), and is standard in enterprise. State management is explicit. |
| **Strands** for agents | AWS-native, built-in MCP support, works with Bedrock natively. The agent-as-tool pattern is well-suited for the specialist sub-agent structure. |
| **MCP** for tools | Open standard, swappable transport (stdio locally → HTTP in AWS). Tools are defined once and work with any compliant agent framework. |
| **DuckDB** for KDB POC | No license needed, reads Parquet directly, fast analytics via SQL. Designed to be swapped for real KDB+/pykx in production. |
| **AMPS** for live data | 60East's market-standard pub/sub for financial data. SOW (State of World) is the key feature — gives snapshot of current state without replaying history. |
| **ChromaDB** locally | No server needed (embedded), works offline, easy to inspect. Replaced by Aurora pgvector in AWS (managed, HA, SQL-queryable). |
| **Haiku for sub-agents** | Sub-agents primarily call tools and format results — they don't need deep reasoning. Haiku is ~20x cheaper and fast enough. Rate limits on Haiku (50K tokens/min input) only hit with 3+ concurrent agents on the same tier. |
| **Keyword routing** | Avoids an extra LLM call for routing. The financial vs general split is clear-cut and stable. The orchestrator (not the router) decides granular tool selection. |
| **Bedrock in production** | No API key management, IAM auth, same Claude models, runs in your VPC. The model IDs use cross-region inference profiles (`us.anthropic.*`) for higher availability. |

---

## 9. Common patterns used throughout the codebase

### Context manager for MCP tools
```python
# Always use the context manager — it handles startup/shutdown of subprocess
with open_amps_tools() as amps_tools:
    if not amps_tools:
        return "AMPS unavailable"
    agent = Agent(model=..., tools=amps_tools)
    return str(agent(query))
```

### Conditional feature enablement
```python
# Features are disabled by default, enabled via env vars
AMPS_ENABLED=false  # set true when AMPS container is running
KDB_ENABLED=false   # set true when parquet data exists
OBSERVABILITY_ENABLED=false  # set true when Langfuse/Phoenix containers are up
```

### Config singleton
```python
# src/config.py — all env vars in one place
from src.config import config
config.AMPS_HOST     # "localhost"
config.AMPS_ENABLED  # True/False
```

### MCP server structure
```python
# Every MCP server follows this pattern:
import mcp.server.stdio
mcp = Server("my-server-name")

@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description — shown to the agent as the tool's docstring."""
    ...
    return result_string

if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run(transport="stdio"))
```

---

## 10. What NOT to do (lessons learned)

1. **Don't use `git add .`** when `.gitignore` has wildcard entries — it can accidentally
   stage files or fail silently. Use `git add <specific-file>` always.

2. **Don't put all agents on Haiku** — you'll hit the 50K input tokens/minute rate limit.
   Use Sonnet for orchestrators that receive large contexts.

3. **Don't use `AMPS.Message` object for publishing** — the AMPS Python client's
   `client.publish()` takes two strings: `(topic, json_string)`. Not a Message object.

4. **Don't ask for clarification before calling tools** — add "CRITICAL: Be proactive"
   to orchestrator system prompts with explicit defaults (last 6 months, HY desk, avg_hit_rate).

5. **Don't read files before editing with Claude Code** — always `Read` before `Edit`.

6. **Don't start services in the wrong order** — AMPS must be running before
   `amps_publisher.py` seeds data. Publisher fails gracefully with a helpful error message.

7. **Don't use `amps_subscribe` when `amps_sow_query` suffices** — SOW returns
   current state much more efficiently than subscribing to the full stream.

---

## 11. Extending the system

### Add a new specialist agent

1. Create `src/agents/my_agent.py`:
   ```python
   def run_my_agent(query: str) -> str:
       with open_my_tools() as tools:
           agent = Agent(model=get_strands_fast_model(), system_prompt=_SYSTEM_PROMPT, tools=tools)
           return str(agent(query))
   ```

2. Add a `@tool` wrapper in `src/agents/financial_orchestrator.py`:
   ```python
   @tool
   def query_my_data(query: str) -> str:
       """Description visible to the orchestrator LLM."""
       from src.agents.my_agent import run_my_agent
       return run_my_agent(query)
   ```

3. Add the tool to the `Financial Orchestrator`'s tools list.

4. Update `_FINANCIAL_KEYWORDS` in `src/agents/orchestrator.py` if needed.

### Add a new MCP server

1. Create `src/mcp_server/my_mcp_server.py` following the Server pattern above.
2. Add a client factory in `src/mcp_clients.py`:
   ```python
   def _my_client() -> MCPClient:
       return MCPClient(lambda: stdio_client(StdioServerParameters(
           command=sys.executable, args=["src/mcp_server/my_mcp_server.py"], env={**os.environ}
       )))
   ```
3. Add a context manager `open_my_tools()` following the `open_amps_tools()` pattern.

### Swap ChromaDB for Aurora pgvector (production)

1. Install: `pip install psycopg2-binary pgvector`
2. In `src/rag/retriever.py`, replace `Chroma(...)` with `PGVector(...)` from `langchain_postgres`.
3. Set env vars: `PGVECTOR_CONNECTION_STRING=postgresql://user:pass@aurora-host/agenticai`
4. Run: `CREATE EXTENSION IF NOT EXISTS vector;` once on the Aurora instance.

---

## 12. Quick reference — model IDs

| Model | Anthropic API | Bedrock (cross-region) |
|-------|--------------|----------------------|
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | `us.anthropic.claude-sonnet-4-6-20251101-v1:0` |
| Claude Haiku 4.5 | `claude-haiku-4-5` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Claude Opus 4.6 | `claude-opus-4-6` | `us.anthropic.claude-opus-4-6-20251101-v1:0` |

In `src/config.py`:
- `ANTHROPIC_MODEL` → orchestrators (Sonnet)
- `ANTHROPIC_FAST_MODEL` → sub-agents (Haiku)
- `BEDROCK_MODEL` → orchestrators in AWS (Sonnet Bedrock ID)

In AWS, `get_strands_fast_model()` always uses the Haiku Bedrock ID hardcoded in
`model_factory.py` (no separate `BEDROCK_FAST_MODEL` config var needed currently).

---

## 13. Verifying real-time AMPS data flow

### The canary test technique

File: `scripts/test_amps_realtime.py`

The script proves end-to-end that the system reads **live data from AMPS SOW**
and not from KDB historical data or any cache layer:

```
Step 1 — Publish position with PnL = 7,777,777.77  (impossible in real financial data)
Step 2 — Query AMPS agent: "What is the current PnL for T_HY_001 on US345370CY87?"
Step 3 — Assert: 7,777,777.77 appears in the response  →  PASS = data came from AMPS
Step 4 — Update same SOW key: PnL = 9,999,999.99
Step 5 — Re-query and assert: 9,999,999.99 appears, 7,777,777.77 is gone
         →  PASS = SOW is truly state-of-world, live updates reflected instantly
Step 6 — Cleanup: zero out the canary record
```

```bash
# Run (requires AMPS_ENABLED=true and AMPS container running)
python scripts/test_amps_realtime.py
python scripts/test_amps_realtime.py --verbose   # full agent responses

# Expected output:
#   [PASS] V1 canary present in live data: canary value 7,777,777.77 found in response.
#   [PASS] V2 canary present after live update: canary value 9,999,999.99 found in response.
#   [PASS] Old canary value 7,777,777.77 no longer in response (SOW replaced).
#   RESULT: ALL TESTS PASSED ✓
```

### Why canary values work

KDB synthetic data uses realistic PnL values (±$50K maximum). A value like
`7,777,777.77` is structurally impossible in the dataset. If the agent returns
it, the data can only have come from AMPS. This eliminates any ambiguity about
data source even if both systems have records for the same trader/ISIN.

The `float` TypeError fix: the `in` operator requires string on the left side
when checking membership in a string. Always format the float first:
```python
# Correct
canary_str = f"{CANARY_PNL_V1:,.2f}".replace(",", "")
ok = canary_str not in response.replace(",", "")

# Wrong — raises TypeError
ok = CANARY_PNL_V1 not in response
```
