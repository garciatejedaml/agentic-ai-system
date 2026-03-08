# Agentic AI System

A production-grade multi-agent financial data platform built with **LangGraph**, **Strands Agents**, **OpenSearch RAG**, and **AMPS real-time messaging**. Designed for both local Docker development and AWS ECS Fargate production deployment.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Repository Structure](#repository-structure)
3. [Demo Mode — No API Key Required](#demo-mode--no-api-key-required)
4. [Local Development — Quick Start](#local-development--quick-start)
5. [AWS Deployment — Step by Step](#aws-deployment--step-by-step)
6. [Phase History](#phase-history)
7. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
User Query  (OpenAI-compatible REST API — continue.dev, curl, etc.)
      │
      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  api-service :8000  (FastAPI + LangGraph StateGraph)                │
│                                                                     │
│  intake ──► retrieve (OpenSearch RAG) ──► orchestrator ──► format  │
│                                               │                     │
│                                          LLM Router                 │
│                                       (Haiku, 1 call)               │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │  A2A HTTP (parallel)
              ┌────────────────────────────┼─────────────────────────┐
              ▼                            ▼                         ▼
       ┌─────────────┐            ┌──────────────┐         ┌────────────────┐
       │  kdb-agent  │            │  amps-agent  │         │ portfolio /    │
       │   :8001     │            │   :8002      │         │ cds / etf /    │
       │ Historical  │            │ AMPS real-   │         │ risk-pnl agent │
       │ bond RFQs   │            │ time SOW     │         │ :8004–:8007    │
       └──────┬──────┘            └──────┬───────┘         └───────┬────────┘
              │                          │ MCP (stdio)             │ MCP (stdio)
              │ MCP (stdio)     ┌────────┴────────┐       ┌────────┴─────────┐
              ▼                 ▼                 ▼       ▼                  ▼
       kdb_mcp_server   AMPS Core :9007    AMPS Products  portfolio_mcp    cds/etf/risk
       (parquet/DuckDB) positions/orders   :9008–:9011    mcp_server       mcp_server
                        market-data        nav/spreads/
                                           etf/risk
```

### Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Gateway | **FastAPI + LangGraph** | Flow control, RAG, A2A dispatch |
| Routing | **LLM Router (Haiku)** | Single LLM call → JSON agent selection |
| Agents | **Strands Agents (AWS)** | Specialist agents with MCP tool use |
| Real-time | **AMPS (60East)** | State-of-World pub/sub message bus |
| Knowledge | **OpenSearch k-NN** | Semantic + BM25 hybrid RAG |
| Registry | **DynamoDB** | Agent discovery (LocalStack in dev) |
| LLM | **Amazon Bedrock** (prod) / **Anthropic API** / **Ollama** (local) | Claude Sonnet + Haiku |
| Observability | **Dynatrace OTel** + Phoenix/Langfuse | Enterprise APM + LLM tracing |

### Specialist Agents

| Agent | Port | Data Source | Timeout |
|-------|------|-------------|---------|
| `kdb-agent` | 8001 | KDB+/DuckDB parquet (historical bond RFQs) | 90s |
| `amps-agent` | 8002 | AMPS live SOW — RAG-driven host:port discovery | 30s |
| `financial-orchestrator` | 8003 | Phase 2 legacy (fallback) | 90s |
| `portfolio-agent` | 8004 | Portfolio holdings, NAV, exposure | 60s |
| `cds-agent` | 8005 | CDS spreads, term structures, credit risk | 60s |
| `etf-agent` | 8006 | ETF NAV, flows, basket composition | 60s |
| `risk-pnl-agent` | 8007 | VaR, DV01, CS01, P&L attribution | 90s |

### AMPS Topics

| Instance | Admin | TCP | Topics |
|----------|-------|-----|--------|
| amps-core | 8085 | 9007 | `positions`, `orders`, `market-data` |
| amps-portfolio | 8086 | 9008 | `portfolio_nav` |
| amps-cds | 8087 | 9009 | `cds_spreads` |
| amps-etf | 8088 | 9010 | `etf_nav` |
| amps-risk | 8089 | 9011 | `risk_metrics` |

---

## Repository Structure

This is a **mono-repo** with 5 sub-repositories. Each one maps to a different deployment concern.

```
agentic-ai-system/
├── .env.example             # Master env template — copy to .env
├── repo-api/                # ★ Core: all Python services (API + agents)
├── repo-mcp-tools/          # MCP servers + AMPS Docker configs
├── repo-rag-ingest/         # RAG knowledge base documents + ingest scripts
├── repo-local-dev/          # Docker Compose files + local dev scripts
└── repo-infra/              # Terraform — AWS infrastructure (prod)
```

---

### `repo-api/` — Python Services

Single Docker image that runs all 8 Python services. Which service starts is controlled by the `AGENT_SERVICE` environment variable read in `docker/phase3_entrypoint.sh`.

```
repo-api/
├── Dockerfile                        # Multi-service image (Python 3.12, ~600 MB)
├── docker/
│   ├── entrypoint.sh                 # API gateway: RAG ingest → uvicorn :8000
│   └── phase3_entrypoint.sh          # Agent selector (AGENT_SERVICE=kdb|amps|portfolio|…)
├── requirements.txt                  # All Python dependencies
└── src/
    ├── config.py                     # ★ Central config — all env vars in one place
    ├── observability.py              # OTEL TracerProvider → Phoenix + Langfuse + Dynatrace
    ├── mcp_clients.py                # ExitStack-based MCP subprocess launcher
    │
    ├── api/
    │   ├── server.py                 # FastAPI app — OpenAI-compatible endpoint
    │   ├── sessions.py               # DynamoDB-backed conversation memory (24h TTL)
    │   └── rate_limiter.py           # Daily per-user request counter (DynamoDB)
    │
    ├── graph/                        # LangGraph StateGraph
    │   ├── state.py                  # AgentState TypedDict
    │   ├── nodes.py                  # intake, retrieve, strands, format nodes
    │   └── workflow.py               # build_graph() + recursion_limit guardrail
    │
    ├── rag/
    │   └── retriever.py              # OpenSearch k-NN + BM25 hybrid retriever
    │
    ├── agents/
    │   ├── model_factory.py          # get_strands_model() — anthropic/bedrock/ollama/mock
    │   ├── llm_router.py             # 1 Haiku call → RouterDecision (agents + strategy)
    │   ├── orchestrator.py           # Entry point: financial vs general routing
    │   ├── researcher.py             # Strands Researcher agent (max_iterations guardrail)
    │   ├── synthesizer.py            # Strands Synthesizer agent (no tools)
    │   ├── kdb_agent.py              # KDB historical analytics specialist
    │   ├── amps_agent.py             # AMPS real-time data specialist
    │   ├── portfolio_agent.py        # Portfolio holdings specialist
    │   ├── cds_agent.py              # CDS spreads specialist
    │   ├── etf_agent.py              # ETF analytics specialist
    │   └── risk_pnl_agent.py         # VaR / P&L specialist
    │
    ├── services/                     # A2A FastAPI wrappers (one per agent)
    │   ├── kdb_agent_service.py      # Exposes kdb-agent on :8001
    │   ├── amps_agent_service.py     # Exposes amps-agent on :8002
    │   └── …                         # (portfolio, cds, etf, risk_pnl)
    │
    └── a2a/
        ├── client.py                 # HTTP A2A call (httpx async)
        ├── registry.py               # DynamoDB agent URL discovery + fallback
        └── parallel_client.py        # asyncio.gather — per-agent timeout via config
```

**LLM Provider selection** (set `LLM_PROVIDER` in `.env`):

| Value | When to use | API key |
|-------|-------------|---------|
| `anthropic` | Local dev (best quality) | `ANTHROPIC_API_KEY` required |
| `ollama` | Local dev (free, no key) | None — Ollama running natively |
| `bedrock` | AWS production | None — IAM role on ECS task |
| `mock` | CI / infra testing | None — canned generic responses |

> **Demo mode** (`DEMO_MODE_ENABLED=true`) works on top of any provider. Scripted financial responses are served instantly for matched queries; unmatched queries fall through to the selected `LLM_PROVIDER`. See [Demo Mode](#demo-mode--no-api-key-required).

---

### `repo-mcp-tools/` — MCP Servers

Model Context Protocol servers that expose financial data tools to Strands agents. Each server runs as a **subprocess (stdio transport)** inside the agent container.

```
repo-mcp-tools/
├── amps_mcp_server.py          # AMPS tools: amps_sow_query, amps_subscribe
├── kdb_mcp_server.py           # KDB tools: kdb_query_rfq_history, kdb_get_analytics
├── portfolio_mcp_server.py     # Portfolio tools: get_portfolio_holdings, get_nav
├── cds_mcp_server.py           # CDS tools: get_cds_spreads, get_term_structure
├── etf_mcp_server.py           # ETF tools: get_etf_nav, get_etf_flows
├── risk_mcp_server.py          # Risk tools: get_var, get_dv01, get_pnl_attribution
└── docker/amps/
    ├── config.xml              # AMPS core instance (positions, orders, market-data)
    ├── config-portfolio.xml    # AMPS portfolio_nav instance
    ├── config-cds.xml          # AMPS cds_spreads instance
    ├── config-etf.xml          # AMPS etf_nav instance
    ├── config-risk.xml         # AMPS risk_metrics instance
    └── AMPS.tar                # ← NOT included (proprietary binary; see Prerequisites)
```

**Adding a new MCP tool:** Create a new `@tool`-decorated function in the relevant server, then re-start the agent container.

---

### `repo-rag-ingest/` — Knowledge Base

Documents ingested into OpenSearch on startup. Uses a **two-tier strategy** for AMPS routing:

```
repo-rag-ingest/
├── data/
│   ├── sample_docs/            # General financial domain knowledge
│   ├── amps_connections/       # Tier 1: one card per AMPS instance (host:port, ~250 chars)
│   └── amps_schemas/           # Tier 2: field-level schema for each AMPS topic
└── scripts/
    ├── ingest_docs.py           # Ingest general docs into OpenSearch
    └── ingest_amps_schemas.py   # Ingest connection cards + schemas
```

**Tier 1 — Connection cards** (tiny, one chunk each):
- The `amps-agent` RAG-searches these to discover `host:port` before making any AMPS call
- ~77 tokens per lookup vs ~3200 tokens with naive chunking

**Tier 2 — Schema docs** (split by `##` section):
- Field names, types, filter examples, full JSON samples per topic
- Allows agents to answer "what fields does cds_spreads have?" from RAG alone

Re-ingest after changing docs:
```bash
docker exec agentic-ai-phase3-api python scripts/ingest_amps_schemas.py
# or dry-run:
docker exec agentic-ai-phase3-api python scripts/ingest_amps_schemas.py --dry-run
```

---

### `repo-local-dev/` — Docker Compose Configs

All Docker Compose files for local development. Each compose file is an isolated stack targeting a specific phase or concern.

```
repo-local-dev/
├── docker-compose.phase3.yml       # ★ PRIMARY — Phase 3 stack (no AMPS server required)
├── docker-compose.local.yml        # Full stack including AMPS (requires AMPS.tar)
├── docker-compose.amps.yml         # AMPS-only stack (5 instances: core + 4 products)
├── docker-compose.phase2.yml       # Phase 2 reference (A2A without LLM Router)
├── docker-compose.observability.yml # Langfuse + Phoenix (optional tracing UI)
├── docker-compose.kdb.yml          # KDB+ server mode (advanced, needs q binary)
├── docker-compose.localstack.yml   # LocalStack DynamoDB only
└── scripts/
    ├── amps_publisher.py            # Publishes positions/orders/market-data to AMPS core
    ├── product_publishers.py        # Publishes portfolio_nav/cds/etf/risk every ~7s
    └── localstack_init.sh           # Creates DynamoDB tables on LocalStack startup
```

**Which compose to use:**

| Goal | Command |
|------|---------|
| Full local dev (Phase 3, no AMPS) | `docker-compose.phase3.yml` |
| Full local dev with live AMPS data | `docker-compose.amps.yml` + `docker-compose.phase3.yml` |
| Observability UI (Langfuse + Phoenix) | `docker-compose.observability.yml` |
| Infra testing only (no LLM) | `LLM_PROVIDER=mock` + `docker-compose.phase3.yml` |

---

### `repo-infra/` — AWS Terraform

Terraform code to deploy the complete system to AWS. See [AWS Deployment](#aws-deployment--step-by-step) below for the full guide.

```
repo-infra/
├── main.tf             # Provider config + S3 backend (commented out, ready to activate)
├── variables.tf        # All input vars (environment, region, cross-region failover, etc.)
├── locals.tf           # Computed: name_prefix, Bedrock model IDs, ECR image URI
├── outputs.tf          # ALB DNS, ECR URL, cluster name, DynamoDB table names, etc.
├── networking.tf       # VPC, 3 subnet tiers (public/private/isolated), NAT, SGs
├── vpc_endpoints.tf    # 6 interface endpoints (Bedrock, ECR×2, Secrets, CWL, SQS) + S3 GW
├── ecr.tf              # ECR repo + lifecycle policy (keep 5 tagged releases)
├── iam.tf              # ECS task role (Bedrock+SQS+DynamoDB) + execution role
├── data.tf             # DynamoDB (agent-registry, sessions, token-usage) + Aurora + SQS + Secrets
├── ecs.tf              # ECS cluster + 8 task definitions + services (API + 7 agents)
├── alb.tf              # ALB + target groups + routing rules
├── autoscaling.tf      # CPU/memory auto-scaling for api-service (1–4 tasks)
├── opensearch.tf       # Amazon OpenSearch Service (t3.small staging / m6g.large prod)
└── cross_region.tf     # Route53 health check + DynamoDB Global Tables replica
```

---

## Demo Mode — No API Key Required

Demo mode serves pre-scripted, realistic financial responses **without any LLM API call**. Designed for presentations on corporate machines where API keys are unavailable or internet access is restricted.

### How it works

```
Your query  →  API (server.py)
                  │
                  ▼
          DEMO_MODE_ENABLED check
                  │
        ┌─────────┴──────────┐
        │                    │
   keyword match?       no match
        │                    │
        ▼                    ▼
  scripted response    LLM_PROVIDER
  (instant, no LLM)   (ollama / mock)
```

1. Every incoming query is checked against 10 pre-scripted financial scenarios in [`demo_responses.py`](repo-api/src/agents/demo_responses.py)
2. If a keyword matches → returns the scripted response **instantly** (no LLM, no network, no API key)
3. If no match → falls through to `LLM_PROVIDER` (use `mock` for a safe generic fallback, or `ollama` for real intelligence on off-script questions)

### Demo scenarios

| Query keywords | What you get |
|----------------|-------------|
| `portfolios`, `list portfolios`, `show portfolios` | Overview of all 5 portfolios with NAV ($1.34B total) |
| `hy`, `high yield`, `hy_main` | HY_MAIN top 10 holdings — Ford, Sprint, Carnival, etc. |
| `ig`, `investment grade`, `ig_core` | IG_CORE top 10 — Apple, JPMorgan, Microsoft |
| `em`, `emerging`, `em_blend` | EM_BLEND exposure by sector — Brazil, Mexico, Indonesia |
| `cds`, `credit default swap`, `spread` | CDS spread table — 50 entities from distressed (Ukraine 1,854 bps) to IG (MSFT 18 bps) |
| `rfq`, `trader`, `hit rate`, `kdb` | Top traders by hit rate — desk rankings, RFQ volume, notional |
| `etf`, `etf flows`, `fund flows` | ETF flow data — LQD, HYG, TLT, AGG, EMB inflows/outflows |
| `var`, `risk`, `dv01`, `p&l`, `pnl` | Risk & P&L dashboard — VaR, DV01, CS01, stress scenarios |
| `rates`, `treasury`, `rates_gov` | RATES_GOV holdings — UST, Agency, TIPS curve positioning |
| `help`, `capabilities`, `what can you do`, `demo` | System overview — architecture, what each agent does |

### Setup on a corporate VDI (no internet API key needed)

**Prerequisites:**
- Docker Desktop installed and running (4 GB RAM minimum)
- Git access to this repository
- No API key, no internet required for demo queries

**Step 1 — Clone the repo**
```bash
git clone https://github.com/garciatejedaml/agentic-ai-system.git
cd agentic-ai-system
```

**Step 2 — Configure `.env`**
```bash
cp .env.example .env
```

Open `.env` and set:
```bash
# ── Demo mode ─────────────────────────────────────────────────
DEMO_MODE_ENABLED=true

# ── LLM fallback for off-script questions ─────────────────────
LLM_PROVIDER=mock        # safest — no dependencies, works fully offline
# LLM_PROVIDER=ollama    # better — real intelligence for off-script questions
                         # (requires: brew install ollama && ollama pull llama3.2:3b)
```

Leave all other vars (ANTHROPIC_API_KEY, etc.) empty or as-is — they are not used in demo mode.

**Step 3 — Build the image** *(~5 min first time)*
```bash
docker compose -f repo-local-dev/docker-compose.phase3.yml build
```

**Step 4 — Start the stack**
```bash
docker compose -f repo-local-dev/docker-compose.phase3.yml --env-file .env up -d

# Watch startup (takes ~60–90s — OpenSearch + RAG ingest):
docker compose -f repo-local-dev/docker-compose.phase3.yml logs -f api-service
# Ready when you see: "Application startup complete"
```

**Step 5 — Verify**
```bash
curl http://localhost:8000/
# Expected: {"status":"ok","service":"Agentic AI System","version":"2.0.0"}
```

**Step 6 — Run demo queries**
```bash
# Portfolio overview (scripted, instant)
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"show me the portfolios"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"

# High Yield holdings
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"show me high yield holdings"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"

# CDS spreads
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"CDS spreads"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"

# Top traders by hit rate
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"who are the top traders by hit rate?"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"

# Risk & VaR
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"show me VaR and risk metrics"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"

# System overview (good opening slide)
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"what can you do?"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

### Using with continue.dev or a chat UI

The API is **OpenAI-compatible**. Point any tool that accepts a custom base URL:

```
Base URL:  http://localhost:8000/v1
API Key:   demo          (any non-empty string)
Model:     agentic-ai    (any string)
```

For **continue.dev** (`~/.continue/config.json`):
```json
{
  "models": [{
    "title": "Agentic AI (Demo)",
    "provider": "openai",
    "model": "agentic-ai",
    "apiBase": "http://localhost:8000/v1",
    "apiKey": "demo"
  }]
}
```

### Stop the demo stack

```bash
docker compose -f repo-local-dev/docker-compose.phase3.yml down
# Add -v to also wipe OpenSearch/DynamoDB data (needed for a clean restart)
```

---

## Local Development — Quick Start

### Prerequisites

1. **Docker Desktop** — [download here](https://www.docker.com/products/docker-desktop/)
   - Allocate at least **4 GB RAM**: `Settings → Resources → Memory → 4 GB`
   - Enable Rosetta on Apple Silicon: `Settings → General → Use Rosetta for x86/amd64 emulation`

2. **LLM — pick one:**
   - **Anthropic API** (best quality): key at [console.anthropic.com](https://console.anthropic.com)
   - **Ollama** (free, no key): see [Ollama setup](#option-b-ollama-free) below
   - **Mock** (no LLM, infra testing): set `LLM_PROVIDER=mock`

3. **AMPS binary** (optional — for live real-time data):
   - Register at [crankuptheamps.com/evaluate](https://crankuptheamps.com/evaluate)
   - Place at `repo-mcp-tools/docker/amps/AMPS.tar`
   - Without this, all agents still work using POC static data via MCP servers

---

### Step 1 — Clone and configure

```bash
git clone https://github.com/garciatejedaml/agentic-ai-system.git
cd agentic-ai-system

cp .env.example .env
# Edit .env — choose your LLM provider (see below)
```

**Option A — Anthropic API:**
```bash
# In .env:
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_FAST_MODEL=claude-haiku-4-5-20251001
```

**Option B — Ollama (free, no API key):** <a name="option-b-ollama-free"></a>
```bash
# 1. Install Ollama natively on Mac (uses Metal GPU — faster than Docker):
brew install ollama && ollama serve

# 2. Pull a model (first time only):
ollama pull llama3.2:3b          # fast, 2 GB RAM
# or
ollama pull qwen2.5:7b           # best tool use, 5 GB RAM (recommended)

# 3. In .env:
LLM_PROVIDER=ollama
# OLLAMA_BASE_URL defaults to http://host.docker.internal:11434 — no change needed
```

**Option C — Mock (infra testing, no LLM):**
```bash
# In .env:
LLM_PROVIDER=mock
# All agents start; responses are placeholder text — no API key required
```

---

### Step 2 — Build the Docker image

```bash
# Build the single multi-service image (Python 3.12 + all deps)
# This takes ~5 min the first time (downloads sentence-transformers, DuckDB, etc.)
docker compose -f repo-local-dev/docker-compose.phase3.yml build
```

---

### Step 3 — Start Phase 3 stack

```bash
docker compose -f repo-local-dev/docker-compose.phase3.yml --env-file .env up -d

# Watch startup (OpenSearch + RAG ingest takes ~60–90s on first run):
docker compose -f repo-local-dev/docker-compose.phase3.yml logs -f api-service
```

Services started:

| Container | Port | Status indicator |
|-----------|------|-----------------|
| `localstack-phase3` | 4566 | `/_localstack/health` returns `{"services":{"dynamodb":"available"}}` |
| `opensearch-phase3` | 9200 | `/_cluster/health` returns `"status":"green"` |
| `kdb-agent-phase3` | 8001 | `/health` returns 200 |
| `amps-agent-phase3` | 8002 | `/health` returns 200 |
| `financial-orchestrator-phase3` | 8003 | `/health` returns 200 |
| `portfolio-agent-phase3` | 8004 | `/health` returns 200 |
| `cds-agent-phase3` | 8005 | `/health` returns 200 |
| `etf-agent-phase3` | 8006 | `/health` returns 200 |
| `risk-pnl-agent-phase3` | 8007 | `/health` returns 200 |
| `api-service-phase3` | 8000 | `/` returns `{"status":"ok"}` |

---

### Step 4 — Verify

```bash
# API gateway
curl http://localhost:8000/

# All agents healthy (expect agent card JSON with "name" field)
for p in 8001 8002 8004 8005 8006 8007; do
  echo "=== :$p ===" && curl -s http://localhost:$p/.well-known/agent.json | python3 -m json.tool | grep '"name"'
done

# OpenSearch RAG docs loaded (expect count > 0)
curl -s http://localhost:9200/knowledge_base/_count | python3 -m json.tool

# DynamoDB agent registry populated
aws --endpoint-url http://localhost:4566 dynamodb scan \
  --table-name agentic-ai-staging-agent-registry \
  --region us-east-1 --output json | python3 -m json.tool | grep agent_id
```

---

### Step 5 — Run queries

**OpenAI-compatible endpoint** (works with continue.dev, Cursor, LM Studio, etc.):

```bash
# General query → Researcher + Synthesizer
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"agentic-ai","messages":[{"role":"user","content":"What is a CDS spread?"}]}'

# Financial query → LLM Router routes to CDS agent
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"agentic-ai","messages":[{"role":"user","content":"What are current CDS spreads for Ford Motor Credit?"}]}'

# Cross-asset parallel query (LLM Router dispatches to multiple agents simultaneously)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"agentic-ai",
    "messages":[{"role":"user","content":"Give me HY portfolio NAV, CDS spreads for Ford, and VaR for all portfolios. I need everything at once."}]
  }'

# Multi-turn session (session_id persisted in DynamoDB)
SESSION=$(curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"agentic-ai","messages":[{"role":"user","content":"Who are the top HY traders?"}],"user":"T_HY_001"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"agentic-ai\",\"messages\":[{\"role\":\"user\",\"content\":\"What bonds are they trading?\"}],\"session_id\":\"$SESSION\"}"
```

**Direct A2A call to a specialist agent:**

```bash
curl -X POST http://localhost:8004/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","method":"tasks/send","id":"t1",
    "params":{"id":"t1","message":{"parts":[{"text":"Show me portfolio NAV for all HY desks"}]}}
  }'
```

---

### Step 6 — Add live AMPS data (optional)

```bash
# Start AMPS stack first (requires AMPS.tar binary)
docker compose -f repo-local-dev/docker-compose.amps.yml up -d

# Start product publishers (simulates live data every ~7s)
python repo-local-dev/scripts/product_publishers.py --mode both --interval 7

# Verify AMPS topics are populated
curl http://localhost:8085/amps.json | python3 -m json.tool | grep '"name"'
# Expected: orders, positions, market-data, portfolio_nav, cds_spreads, etf_nav, risk_metrics
```

---

### Step 7 — Optional: Observability UI

```bash
# Start Langfuse + Phoenix (separate stack)
docker compose -f repo-local-dev/docker-compose.observability.yml up -d

# Enable tracing in .env:
OBSERVABILITY_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# Restart api-service to pick up new env
docker compose -f repo-local-dev/docker-compose.phase3.yml restart api-service

# UIs:
# Langfuse (graph view + metrics):  http://localhost:3000
# Phoenix (RAG + span analysis):     http://localhost:6006
```

---

### Stop the stack

```bash
docker compose -f repo-local-dev/docker-compose.phase3.yml down

# Remove volumes (clears OpenSearch index, DynamoDB tables, LocalStack data):
docker compose -f repo-local-dev/docker-compose.phase3.yml down -v
```

---

## AWS Deployment — Step by Step

The `repo-infra/` Terraform deploys the full Phase 3/4 system to AWS using **ECS Fargate** + **Amazon Bedrock** (no API key required — IAM role auth).

### AWS Architecture

```
                         ┌──────────────────────────────────────────────┐
Internet ───► ALB :80 ───► api-service  (ECS Fargate, private subnet)   │
                         │  LangGraph + LLM Router + Strands agents      │
                         └──────────────────────────┬───────────────────┘
                                                    │ IAM (no API key)
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                              Amazon Bedrock   OpenSearch    DynamoDB
                           (Sonnet + Haiku)   (private VPC)  (Global Tables)
                              (cross-region                   sessions +
                              inference)                      agent-registry
                                    │
                       ┌────────────┼────────────────────────┐
                       ▼           ▼           ▼             ▼
               kdb-agent   amps-agent  portfolio-agent  cds/etf/risk
              (ECS Fargate)(ECS Fargate)(ECS Fargate)   (ECS Fargate)
              :8001        :8002        :8004            :8005-:8007
```

**Key design decisions for production (JP Morgan / corporate AWS):**
- `LLM_PROVIDER=bedrock` — no Anthropic API key needed; auth via ECS task IAM role
- `LLM_PROVIDER=mock` — for infra deployment before API keys are approved
- All services communicate via ECS internal DNS (`.local` suffix) — no ALB for agent-to-agent calls
- OpenSearch in private VPC subnet — only ECS app SG can reach port 443
- Secrets injected at container start from Secrets Manager (never in env vars)
- DynamoDB Global Tables with replica in `us-west-2` for session memory backup

---

### Prerequisites

```bash
# Terraform 1.5+
terraform --version

# AWS CLI configured with deployment credentials
aws configure
aws sts get-caller-identity   # verify credentials + account ID

# Docker (for ECR image build)
docker --version

# jq (for parsing secrets output)
brew install jq
```

---

### Step 1 — Configure Terraform variables

```bash
cd repo-infra

# Copy the example file
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
aws_region   = "us-east-1"
environment  = "staging"          # "staging" | "production"
app_name     = "agentic-ai"

# Image tag — set to "latest" for initial deploy; use git SHA in CI/CD
image_tag    = "latest"

# Infra scale
task_cpu         = 1024           # 1 vCPU
task_memory      = 2048           # 2 GB
service_max_count = 4

# Phase 4: Cross-region failover (set to true when ready for multi-region)
cross_region_failover_enabled = false
secondary_region              = "us-west-2"
# route53_zone_id             = "Z1234567890"  # required if failover enabled

# AMPS (set to "true" when AMPS servers are deployed)
amps_enabled = "false"

# Skip RAG re-ingest on subsequent deploys (set true after first successful deploy)
skip_ingest  = "false"
```

---

### Step 2 — Configure remote state (recommended for teams)

```bash
# Create S3 bucket for Terraform state
aws s3 mb s3://my-company-tf-state --region us-east-1
aws s3api put-bucket-versioning \
  --bucket my-company-tf-state \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# Uncomment the backend "s3" block in repo-infra/main.tf:
# backend "s3" {
#   bucket         = "my-company-tf-state"
#   key            = "agentic-ai/staging/terraform.tfstate"
#   region         = "us-east-1"
#   dynamodb_table = "terraform-state-lock"
#   encrypt        = true
# }
```

---

### Step 3 — Initialize and plan

```bash
cd repo-infra

terraform init
terraform plan -out=tfplan

# Review the plan — expected resources:
# + aws_vpc, subnets, NAT gateway, security groups
# + aws_ecs_cluster + 8 task definitions + 8 services
# + aws_opensearch_domain (t3.small for staging)
# + aws_dynamodb_table (agent-registry, sessions, token-usage)
# + aws_lb + target groups
# + aws_ecr_repository
# + aws_secretsmanager_secret
# + aws_iam_role (task + execution)
# + 6 VPC interface endpoints (Bedrock, ECR×2, Secrets, CWL, SQS)
```

---

### Step 4 — Apply infrastructure

```bash
terraform apply tfplan
```

> This takes ~15–20 minutes. OpenSearch domain creation is the slowest step (~10 min).
> ECS services will be created but the health checks will fail until the Docker image is pushed (Step 5).

Save the outputs for later steps:
```bash
terraform output
# Expected outputs:
# alb_dns_name           = "agentic-ai-staging-alb-XXXXXX.us-east-1.elb.amazonaws.com"
# ecr_api_repository_url = "ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/agentic-ai-staging-api"
# ecs_cluster_name       = "agentic-ai-staging-cluster"
# app_secret_arn         = "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:/agentic-ai-staging/app/secrets-XXXX"
# opensearch_endpoint    = "https://XXXX.us-east-1.es.amazonaws.com"
```

---

### Step 5 — Build and push the Docker image

Run from the **monorepo root** (not `repo-infra/`):

```bash
# Get ECR URL from Terraform output
ECR_URL=$(terraform -chdir=repo-infra output -raw ecr_api_repository_url)
IMAGE_TAG=$(git rev-parse --short HEAD)

# Authenticate to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin "${ECR_URL%/*}"

# Build for Linux/amd64 (required for Fargate, even on Apple Silicon)
docker build \
  --platform linux/amd64 \
  -f repo-api/Dockerfile \
  -t "${ECR_URL}:${IMAGE_TAG}" \
  -t "${ECR_URL}:latest" \
  .

# Push both tags
docker push "${ECR_URL}:${IMAGE_TAG}"
docker push "${ECR_URL}:latest"

echo "Image pushed: ${ECR_URL}:${IMAGE_TAG}"
```

---

### Step 6 — Deploy with the correct image tag

```bash
cd repo-infra
TF_VAR_image_tag=${IMAGE_TAG} terraform apply -auto-approve
```

This updates all 8 ECS task definitions to use the new image tag and triggers rolling deployments.

---

### Step 7 — Set secrets in Secrets Manager

```bash
SECRET_ARN=$(terraform -chdir=repo-infra output -raw app_secret_arn)

# For LLM_PROVIDER=bedrock (JP Morgan production): ANTHROPIC_API_KEY not needed
# For LLM_PROVIDER=mock (initial infra testing): leave ANTHROPIC_API_KEY as REPLACE_ME

aws secretsmanager put-secret-value \
  --secret-id "${SECRET_ARN}" \
  --secret-string "$(cat <<'EOF'
{
  "ANTHROPIC_API_KEY":   "REPLACE_ME",
  "BRAVE_API_KEY":       "REPLACE_ME",
  "LANGFUSE_PUBLIC_KEY": "REPLACE_ME",
  "LANGFUSE_SECRET_KEY": "REPLACE_ME",
  "DYNATRACE_API_TOKEN": "REPLACE_ME"
}
EOF
)"
```

> **JP Morgan production:**
> - `ANTHROPIC_API_KEY` → `REPLACE_ME` (Bedrock uses IAM, no API key needed)
> - `DYNATRACE_API_TOKEN` → your Dynatrace `dt0c01.xxx` token (enables enterprise APM tracing)
> - `BRAVE_API_KEY` → optional (web search tool)

---

### Step 8 — Force ECS redeployment

```bash
CLUSTER=$(terraform -chdir=repo-infra output -raw ecs_cluster_name)

# Redeploy all 8 services to pick up new secrets
for svc in api kdb-agent amps-agent financial-orchestrator portfolio-agent cds-agent etf-agent risk-pnl-agent; do
  SVC_NAME="agentic-ai-staging-${svc}"
  echo "Redeploying ${SVC_NAME}..."
  aws ecs update-service \
    --cluster "${CLUSTER}" \
    --service "${SVC_NAME}" \
    --force-new-deployment \
    --no-cli-pager
done
```

Wait for all services to be healthy:
```bash
# Watch ECS service stability (Ctrl+C to stop watching)
aws ecs wait services-stable \
  --cluster "${CLUSTER}" \
  --services agentic-ai-staging-api agentic-ai-staging-kdb-agent agentic-ai-staging-portfolio-agent
```

---

### Step 9 — Verify deployment

```bash
ALB=$(terraform -chdir=repo-infra output -raw alb_dns_name)

# API gateway health
curl -s "http://${ALB}/"

# Test financial query (Bedrock → LLM Router → specialist agents)
curl -s "http://${ALB}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agentic-ai",
    "messages": [{"role": "user", "content": "What are the top HY bond traders by hit rate this month?"}]
  }' | python3 -m json.tool

# Test RAG query
curl -s "http://${ALB}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"agentic-ai","messages":[{"role":"user","content":"What fields does the cds_spreads AMPS topic have?"}]}' \
  | python3 -m json.tool | grep '"content"' | head -3
```

---

### Step 10 — One-time Aurora setup (pgvector)

Aurora Serverless v2 is provisioned but the `vector` extension must be enabled once:

```bash
# Get Aurora credentials
AURORA_CREDS=$(aws secretsmanager get-secret-value \
  --secret-id /agentic-ai-staging/aurora/credentials \
  --query SecretString --output text)

AURORA_HOST=$(terraform -chdir=repo-infra output -raw aurora_endpoint)
AURORA_PASS=$(echo "${AURORA_CREDS}" | jq -r .password)

# Enable pgvector
PGPASSWORD="${AURORA_PASS}" psql \
  -h "${AURORA_HOST}" -U agenticai -d agenticai \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

---

### Step 11 — Enable cross-region failover (production)

When ready to enable session memory backup and Route53 health check:

```bash
# In terraform.tfvars:
# cross_region_failover_enabled = true
# secondary_region              = "us-west-2"
# route53_zone_id               = "Z1234567890"  # your hosted zone

cd repo-infra
terraform plan -var="cross_region_failover_enabled=true"
terraform apply -var="cross_region_failover_enabled=true"
```

This enables:
- **DynamoDB Global Tables** — `sessions` and `agent-registry` automatically replicate to `us-west-2`. Zero code changes. Conversation history survives a regional outage.
- **Route53 health check** — monitors `ALB_DNS/health` every 10s; 3 consecutive failures trigger DNS failover.
- **AMPS** already provides its own cross-region failover via the AMPS URL routing layer — no additional config needed.

---

### CI/CD with GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # OIDC auth (no long-lived keys)
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::ACCOUNT_ID:role/github-actions-deploy
          aws-region: us-east-1

      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build --platform linux/amd64 \
            -f repo-api/Dockerfile \
            -t "$ECR_REGISTRY/agentic-ai-staging-api:$IMAGE_TAG" .
          docker push "$ECR_REGISTRY/agentic-ai-staging-api:$IMAGE_TAG"

      - name: Terraform deploy
        working-directory: repo-infra
        env:
          TF_VAR_image_tag: ${{ github.sha }}
          TF_VAR_skip_ingest: "true"   # docs already indexed from previous deploy
        run: |
          terraform init
          terraform apply -auto-approve
```

---

### Cost Estimate

**Staging (1 API task + 7 agent tasks, us-east-1, ~720 hours/month):**

| Resource | $/month (approx) |
|----------|-----------------|
| ECS Fargate — api-service (1 vCPU, 2 GB) | ~$30 |
| ECS Fargate — 7 agent tasks (0.5 vCPU, 1 GB each) | ~$75 |
| ALB | ~$20 |
| NAT Gateway | ~$35 |
| VPC Interface Endpoints (6) | ~$50 |
| OpenSearch t3.small (20 GB gp3) | ~$25 |
| Aurora Serverless v2 (0.5 ACU, auto-pauses) | ~$5–15 |
| DynamoDB (PAY_PER_REQUEST, ~500 users) | ~$2 |
| CloudWatch Logs | ~$3 |
| **Total staging** | **~$245–260/month** |

**Production (m6g.large OpenSearch + 2 AZs + cross-region):**
- Add ~$200/month for production-grade OpenSearch + DynamoDB Global Tables replica

---

### Destroy infrastructure

```bash
# Disable deletion protection first if production
terraform -chdir=repo-infra apply -var="aurora_deletion_protection=false"

# WARNING: destroys everything including data
terraform -chdir=repo-infra destroy
```

---

## Phase History

| Branch | Key additions |
|--------|--------------|
| `main` (Phase 1) | LangGraph + Strands + ChromaDB RAG + MCP tools |
| `phase/2-a2a-orchestration` | A2A agents, DynamoDB registry, financial orchestrator |
| `phase/3-llm-router-parallel` | LLM Router, 4 specialist agents, OpenSearch RAG, AMPS topics |
| `phase/4-guardrails-multiregion` | Dynatrace OTel, guardrails, cross-region failover, rate limiting |
| `phase/5-mcp-gateway-prompt-registry` | MCP Gateway, HTTP/SSE transport, DynamoDB auto-registration, Langfuse prompt management |
| `phase/6-demo-mode` | Demo mode with pre-scripted financial responses (no API key required), Ollama fallback |

---

## Troubleshooting

### Continue.dev stuck on "Generating…"

Check that `OBSERVABILITY_ENABLED=false` in `docker-compose.phase3.yml`. If Langfuse keys are set but the Langfuse stack isn't running, each request blocks waiting for the trace connection.

```bash
docker exec agentic-ai-phase3-api printenv OBSERVABILITY_ENABLED
# must print: false
```

### MCP background thread timeout

KDB MCP server loads DuckDB + parquet on startup (~30s). If the container is slow:
```bash
docker logs agentic-ai-phase3-api 2>&1 | grep -E "MCP|WARNING|background thread"
```
The system is resilient — if individual MCP servers fail, they are skipped and the agent continues without those tools.

### Anthropic API overloaded (HTTP 529)

Transient rate limit. The system automatically retries with exponential backoff (3 attempts: 5s → 10s → 20s). If it keeps failing, switch to `LLM_PROVIDER=ollama` or `LLM_PROVIDER=mock`.

### OpenSearch OOM (exit code 137)

Increase Docker Desktop RAM to 5+ GB, or reduce OpenSearch JVM heap:
```yaml
# In docker-compose.phase3.yml opensearch service:
OPENSEARCH_JAVA_OPTS: -Xms256m -Xmx256m  # was 128m — increase here
```

### AMPS containers fail to start

Ensure `repo-mcp-tools/docker/amps/AMPS.tar` exists (proprietary binary from 60East).
Without AMPS, all agents work with POC static data via MCP servers.

### api-service takes too long to start (>120s)

First startup ingests RAG docs into OpenSearch and loads the sentence-transformer model (~400 MB). This is a one-time cost. Subsequent starts are fast because docs are idempotently re-indexed (SHA256 content ID — no duplicates).

After the first successful run, set `SKIP_INGEST=true` in `.env` to skip ingestion on restart.

### Rate limit: 429 Too Many Requests

Daily request limit reached for this user. The default is 1000 requests/day.
- In local dev: `RATE_LIMIT_ENABLED=false` (already disabled in `docker-compose.phase3.yml`)
- In AWS: increase `DAILY_REQUEST_LIMIT` or check the `token-usage` DynamoDB table

### Ollama not reachable from containers

```bash
# Verify Ollama is running on the host
curl http://localhost:11434/

# Verify reachable from inside container
docker exec agentic-ai-phase3-api curl -s http://host.docker.internal:11434/

# List available models
ollama list
```

If not running: `ollama serve`. If model not pulled: `ollama pull llama3.2:3b`.
