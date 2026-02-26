# Agentic AI System

A multi-agent financial data platform built with **LangGraph**, **Strands Agents**, **OpenSearch RAG**, and **AMPS real-time messaging** — designed as a fully Dockerized local development environment.

---

## Architecture

```
User Query (REST / OpenAI-compatible chat API)
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                   LangGraph StateGraph                       │
│                    (api-service :8000)                       │
│                                                              │
│  intake ──► retrieve (RAG) ──► orchestrator ──► format      │
│                 │                    │                        │
│             OpenSearch            LLM Router                 │
│          (k-NN + BM25)         (Haiku, 1 call)              │
└───────────────────────────────┬─────────────────────────────┘
                                │ A2A (parallel)
          ┌─────────────────────┼──────────────────────┐
          ▼                     ▼                      ▼
   ┌─────────────┐    ┌─────────────────┐    ┌───────────────┐
   │  KDB Agent  │    │   AMPS Agent    │    │ Portfolio /   │
   │   :8001     │    │    :8002        │    │ CDS / ETF /   │
   │ Historical  │    │ Real-time SOW   │    │ Risk agents   │
   │ bond RFQs   │    │ + RAG routing   │    │ :8004–:8007   │
   └─────────────┘    └────────┬────────┘    └───────────────┘
                               │ MCP tools
                    ┌──────────┴──────────┐
                    ▼                     ▼
            AMPS Core :9007      AMPS Products
            positions / orders   :9008 portfolio_nav
            market-data          :9009 cds_spreads
                                 :9010 etf_nav
                                 :9011 risk_metrics
```

### Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Gateway | **FastAPI + LangGraph** | Flow control, RAG retrieval, A2A dispatch |
| Routing | **LLM Router (Haiku)** | Single LLM call → JSON routing decision |
| Agents | **Strands Agents** | Specialist agents with MCP tool use |
| Real-time data | **AMPS** | State-of-World (SOW) message bus |
| Knowledge | **OpenSearch k-NN** | Semantic vector search (RAG) |
| Registry | **LocalStack DynamoDB** | Agent discovery (AWS-compatible) |
| LLM | **Anthropic API** or **Ollama** | Claude Sonnet/Haiku (cloud) or Llama/Qwen (local, free) |

### Specialist Agents

| Agent | Port | Capabilities |
|-------|------|-------------|
| `kdb-agent` | 8001 | Historical bond RFQ analytics, trade history |
| `amps-agent` | 8002 | Live AMPS data — RAG-driven host:port discovery |
| `financial-orchestrator` | 8003 | Phase 2 legacy orchestrator (fallback) |
| `portfolio-agent` | 8004 | Portfolio holdings, exposure, allocation |
| `cds-agent` | 8005 | CDS spreads, term structures, credit risk |
| `etf-agent` | 8006 | ETF NAV, flows, basket composition |
| `risk-pnl-agent` | 8007 | VaR, DV01, CS01, P&L attribution |

### AMPS Topics

| Instance | Admin | TCP | Topics |
|----------|-------|-----|--------|
| amps-core | 8085 | 9007 | positions, orders, market-data |
| amps-portfolio | 8086 | 9008 | portfolio_nav |
| amps-cds | 8087 | 9009 | cds_spreads |
| amps-etf | 8088 | 9010 | etf_nav |
| amps-risk | 8089 | 9011 | risk_metrics |

---

## Local Setup with Docker Desktop

### Prerequisites

1. **Docker Desktop** — [download here](https://www.docker.com/products/docker-desktop/)
   - Allocate at least **4 GB RAM** to Docker Desktop:
     `Settings → Resources → Memory → 4 GB`
   - Enable Rosetta emulation for the AMPS binary (x86_64 on Apple Silicon):
     `Settings → General → Use Rosetta for x86/amd64 emulation`

2. **LLM — pick one:**
   - **Anthropic API** (best quality): get a key at [console.anthropic.com](https://console.anthropic.com)
   - **Ollama** (free, no key, runs locally): see [Ollama setup](#option-b-ollama-free-no-api-key) below

3. **AMPS binary** (proprietary — required for live data simulation):
   - Register at [crankuptheamps.com/evaluate](https://crankuptheamps.com/evaluate)
   - Place the Linux tarball at: `repo-mcp-tools/docker/amps/AMPS.tar`
   - Without this file the AMPS services won't start, but all other agents still work with POC static data.

---

### Step 1 — Clone and configure

```bash
git clone <repo-url>
cd agentic-ai-system

cp .env.example .env
# Edit .env — see the LLM section below for your choice
```

**Option A — Anthropic API:**

```bash
# In .env:
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Option B — Ollama (free, no API key):** <a name="option-b-ollama-free-no-api-key"></a>

```bash
# 1. Install Ollama on Mac (uses Metal GPU — much faster than Docker):
brew install ollama

# 2. Start Ollama (keep this terminal open, or run as a background service):
ollama serve

# 3. Pull the model (first time only, ~2GB download):
ollama pull llama3.2:3b

# 4. In .env:
LLM_PROVIDER=ollama
# OLLAMA_BASE_URL and OLLAMA_MODEL have sensible defaults — no changes needed
```

> **Model recommendations for Ollama:**
> | Model | RAM | Routing | Tool use | Best for |
> |-------|-----|---------|----------|----------|
> | `llama3.2:3b` | ~2 GB | ✅ Good | ⚠️ Partial | Fast routing, lightweight |
> | `qwen2.5:7b` | ~5 GB | ✅ Excellent | ✅ Good | Best balance (recommended) |
> | `mistral:7b` | ~5 GB | ✅ Good | ✅ Good | Instruction following |
> | `llama3.1:8b` | ~5 GB | ✅ Excellent | ✅ Good | Full agent reasoning |
>
> **Tool use note**: `llama3.2:3b` handles LLM routing well but may struggle with complex
> multi-step MCP tool loops. For full agent tool use, use `qwen2.5:7b` or larger:
> ```bash
> ollama pull qwen2.5:7b
> # In .env:
> OLLAMA_MODEL=qwen2.5:7b
> ```
>
> On Apple Silicon, Ollama uses Metal GPU automatically — expect 20-50 tok/s for 7B models.

---

### Step 2 — Build Docker images

```bash
# Build both images (agentic-ai-api + agentic-ai-amps)
docker compose -f repo-local-dev/docker-compose.local.yml build
```

This builds:
- `agentic-ai-api:latest` — Python service image (agents, API gateway, publishers)
- `agentic-ai-amps:latest` — AMPS server image (requires `AMPS.tar`)

> **First build takes ~5 minutes** — it downloads Python dependencies including
> `sentence-transformers` (~400 MB) and compiles the AMPS Python client.

---

### Step 3 — Start everything

```bash
docker compose -f repo-local-dev/docker-compose.local.yml --env-file .env up -d
```

Services start in dependency order. Wait ~2 minutes for all health checks to pass:

```bash
# Watch startup progress
docker compose -f repo-local-dev/docker-compose.local.yml logs -f
```

---

### Step 4 — Verify

```bash
# API gateway
curl http://localhost:8000/

# All specialist agents (should return agent card JSON)
for p in 8001 8002 8004 8005 8006 8007; do
  echo "=== :$p ===" && curl -s http://localhost:$p/.well-known/agent.json | python3 -m json.tool | grep '"name"'
done

# OpenSearch RAG (should show doc count > 0)
curl -s http://localhost:9200/knowledge_base/_count | python3 -m json.tool

# AMPS core topics (if AMPS binary is installed)
curl -s http://localhost:8085/topics.json | python3 -m json.tool
```

---

### Step 5 — Send queries

**OpenAI-compatible chat endpoint** (works with continue.dev, Cursor, etc.):

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agentic-ai",
    "messages": [{"role": "user", "content": "What are the current CDS spreads for Ford Motor Credit?"}]
  }'
```

**Direct A2A call to a specialist agent:**

```bash
curl -X POST http://localhost:8002/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "id": "t1",
    "params": {
      "id": "t1",
      "message": {"parts": [{"text": "Show me live portfolio NAV for all desks"}]}
    }
  }'
```

**Cross-asset parallel query** (LLM Router dispatches to multiple agents simultaneously):

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agentic-ai",
    "messages": [{"role": "user", "content": "Give me HY portfolio NAV, current CDS spreads for Ford, and today P&L. I need everything at once."}]
  }'
```

---

### Stop the stack

```bash
docker compose -f repo-local-dev/docker-compose.local.yml down

# Remove volumes (clears OpenSearch index, AMPS SOW data, LocalStack tables):
docker compose -f repo-local-dev/docker-compose.local.yml down -v
```

---

## Project Structure

```
agentic-ai-system/
├── .env.example                        # Copy to .env — fill in your API keys
│
├── repo-api/                           # FastAPI gateway + all agent services
│   ├── Dockerfile                      # Single image for all Python services
│   ├── docker/
│   │   ├── entrypoint.sh               # API gateway entrypoint (RAG ingest + uvicorn)
│   │   └── phase3_entrypoint.sh        # Service selector (AGENT_SERVICE env var)
│   └── src/
│       ├── config.py                   # Centralised env-var config
│       ├── api/server.py               # FastAPI app (OpenAI-compatible + A2A)
│       ├── graph/                      # LangGraph: state, nodes, workflow
│       ├── rag/retriever.py            # OpenSearch k-NN RAG retriever
│       ├── agents/
│       │   ├── llm_router.py           # Haiku-based routing (1 LLM call → JSON)
│       │   ├── orchestrator.py         # LangGraph orchestrator node
│       │   ├── amps_agent.py           # RAG-driven AMPS agent (discovers host:port)
│       │   ├── kdb_agent.py            # KDB historical analytics agent
│       │   ├── portfolio_agent.py      # Portfolio holdings agent
│       │   ├── cds_agent.py            # CDS spreads agent
│       │   ├── etf_agent.py            # ETF analytics agent
│       │   └── risk_pnl_agent.py       # Risk & P&L agent
│       ├── services/                   # A2A FastAPI wrappers (one per agent)
│       └── a2a/
│           ├── registry.py             # DynamoDB agent registry
│           └── parallel_client.py      # Concurrent A2A dispatch
│
├── repo-mcp-tools/                     # MCP servers (tools available to Strands agents)
│   ├── amps_mcp_server.py              # amps_sow_query, amps_subscribe, etc.
│   ├── kdb_mcp_server.py               # kdb_query_rfq_history, etc.
│   ├── portfolio_mcp_server.py         # get_portfolio_holdings, etc.
│   ├── cds_mcp_server.py               # get_cds_spreads, etc.
│   └── etf_mcp_server.py              # get_etf_nav, etc.
│   └── docker/amps/                    # AMPS server configs (config.xml per instance)
│
├── repo-rag-ingest/                    # RAG knowledge base sources
│   ├── data/
│   │   ├── sample_docs/                # General domain knowledge
│   │   ├── amps_connections/           # Tier 1: AMPS host:port cards (1 chunk each)
│   │   └── amps_schemas/               # Tier 2: AMPS topic field schemas
│   └── scripts/
│       ├── ingest_docs.py              # Ingest general docs
│       └── ingest_amps_schemas.py      # Ingest AMPS connection cards + schemas
│
└── repo-local-dev/                     # Docker Compose configs + local scripts
    ├── docker-compose.local.yml        # ★ ONE COMMAND — full local stack
    ├── docker-compose.phase3.yml       # Phase 3 only (no AMPS, external OpenSearch)
    ├── docker-compose.amps.yml         # AMPS stack only
    ├── docker-compose.observability.yml # Langfuse tracing (optional)
    └── scripts/
        ├── amps_publisher.py           # Simulates positions/orders/market-data
        ├── product_publishers.py       # Simulates portfolio_nav/cds/etf/risk
        └── localstack_init.sh          # Creates DynamoDB tables on LocalStack startup
```

---

## RAG Knowledge Base

The system uses a two-tier document strategy for AMPS routing:

**Tier 1 — Connection cards** (`repo-rag-ingest/data/amps_connections/`):
- One file per AMPS instance (~250 chars, single chunk)
- The amps-agent searches these to discover `host:port` before any AMPS query
- Result: ~77 tokens per lookup (vs ~3200 with naive chunking)

**Tier 2 — Schema docs** (`repo-rag-ingest/data/amps_schemas/`):
- One file per topic — field names, types, filter examples, JSON samples
- Split by `##` markdown section (tables never cut mid-row)

To re-ingest after changing docs:

```bash
# Inside api-service container
docker exec local-api-service python scripts/ingest_amps_schemas.py

# Or dry-run to preview chunks without ingesting
docker exec local-api-service python scripts/ingest_amps_schemas.py --dry-run
```

---

## Extending the System

### Add a new Strands agent

```python
# repo-api/src/agents/my_agent.py
from strands import Agent
from src.agents.model_factory import get_strands_model

agent = Agent(
    model=get_strands_model(),
    system_prompt="You answer questions about ...",
    tools=[...],
)

async def run(query: str) -> str:
    result = await asyncio.to_thread(agent, query)
    return str(result)
```

Then:
1. Create `repo-api/src/services/my_agent_service.py` (A2A FastAPI wrapper)
2. Add `AGENT_SERVICE: my_agent` case to `phase3_entrypoint.sh`
3. Register the agent in `llm_router.py` `_AGENT_DESCRIPTIONS`
4. Add a service block to `docker-compose.local.yml`

### Add a new AMPS topic

1. Add `<Topic>` block to the relevant `repo-mcp-tools/docker/amps/config*.xml`
2. Add a publisher in `repo-local-dev/scripts/product_publishers.py`
3. Create a connection card at `repo-rag-ingest/data/amps_connections/`
4. Create a schema doc at `repo-rag-ingest/data/amps_schemas/`
5. Re-ingest: `docker exec local-api-service python scripts/ingest_amps_schemas.py`

---

## Troubleshooting

### Ollama not reachable from Docker containers

The most common issue when using `LLM_PROVIDER=ollama` with native Mac Ollama:

```bash
# Verify Ollama is running on the host
curl http://localhost:11434/

# Verify it's reachable from inside a container
docker exec local-api-service curl -s http://host.docker.internal:11434/

# List available models
ollama list
```

If Ollama isn't running: `ollama serve` (keep the terminal open or configure it as a macOS service).

If the model isn't pulled: `ollama pull llama3.2:3b`

### Ollama responses are slow

- On Apple Silicon, confirm Ollama is using Metal (should say `[metal]` in `ollama serve` output)
- Try a smaller model: `ollama pull llama3.2:1b` and set `OLLAMA_MODEL=llama3.2:1b`
- The first request is slower because the model loads into GPU memory; subsequent calls are fast

### Ollama router returns wrong agents

Smaller models (3B and below) occasionally produce malformed JSON or route poorly. If routing
fails, the system falls back to `kdb-agent`. To improve: use a larger model (`qwen2.5:7b` or
`llama3.1:8b`) or use `LLM_PROVIDER=anthropic` for the router specifically.

---

### OpenSearch exits with code 137 (OOM)

Docker Desktop ran out of memory. Either:
- Increase Docker Desktop RAM allocation to 5+ GB
- Stop non-essential services (e.g. Langfuse observability stack)

```bash
docker compose -f repo-local-dev/docker-compose.observability.yml down
```

### AMPS containers fail to start

Ensure `repo-mcp-tools/docker/amps/AMPS.tar` exists. The AMPS binary is proprietary
and must be downloaded separately from [crankuptheamps.com/evaluate](https://crankuptheamps.com/evaluate).

Without AMPS, the portfolio/CDS/ETF/risk agents still work using their POC static data
via MCP tools (`portfolio_mcp_server.py`, `cds_mcp_server.py`, etc.).

### api-service takes too long to start

The first startup ingests RAG docs into OpenSearch and loads the sentence-transformer
model (~400 MB). This can take 60–90 seconds. Subsequent starts are faster because
documents are idempotently re-indexed (SHA256 doc ID — no duplicates).

### Rate limit errors (Anthropic API)

The system uses Haiku for the LLM Router (fast, cheap) and Sonnet for agent reasoning.
If you hit rate limits, set `ANTHROPIC_FAST_MODEL=claude-haiku-4-5-20251001` and
reduce concurrent agent calls by querying simpler (single-agent) questions first.
