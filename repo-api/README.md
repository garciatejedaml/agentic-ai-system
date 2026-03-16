# repo-api — Agentic AI System API

FastAPI service + LangGraph workflow + Strands specialist agents for fixed income trading desks. Traders submit natural language queries; the system routes them to specialist agents in parallel and returns a synthesized answer with per-data-point confidence scores.

All 7 specialist agents and the API gateway are built into **one Docker image**. The `AGENT_SERVICE` environment variable selects which service starts at runtime.

---

## Query Lifecycle

```
State 0 — User Query
  POST /v1/chat/completions  {"messages": [{"role": "user", "content": "..."}]}

State 1 — Session + RAG
  DynamoDB session created (TTL 30 min)
  OpenSearch vector search → agent profiles + desk context injected as system prompt

State 2 — LLM Router  (Haiku — single LLM call, ~300ms, ~$0.0003)
  Reads live agent registry from DynamoDB
  Outputs routing plan:
  {
    "agents": [
      {"id": "kdb-agent",      "priority": "required", "timeout_ms": 90000},
      {"id": "cds-agent",      "priority": "required", "timeout_ms": 60000},
      {"id": "risk-pnl-agent", "priority": "optional", "timeout_ms": 30000}
    ],
    "strategy": "parallel",
    "reasoning": "query needs historical RFQ data + live CDS spreads"
  }

State 3 — Parallel Fan-out  (asyncio.gather)
  Each agent called concurrently with its own timeout_ms
  Timed-out agents → AgentResult(success=False, timed_out=True)

State 4 — Confidence Scoring
  HIGH   — all required agents responded successfully
  MEDIUM — required agents OK; one or more optional agents timed out
  LOW    — at least one required agent timed out or errored

State 5 — Synthesis  (Sonnet — ~2s, 2048 output tokens)
  Reasons across agent results
  Tags each data point: [HIGH] confirmed | [LOW] unavailable or estimated
  Explicitly states missing data when required agents failed

State 6 — Observability  (Langfuse — async, no latency impact)
  Full trace: session_id, routing plan, latency per agent, token usage

State 7 — Response
  Structured answer with confidence score and data gap warnings
```

---

## Agents

| Agent | Port | `AGENT_SERVICE` | Data source | Default timeout |
|-------|------|-----------------|-------------|-----------------|
| `kdb-agent` | 8001 | `kdb` | KDB+ / S3 Parquet (6-month bond RFQ) | 90s |
| `amps-agent` | 8002 | `amps` | AMPS Core — positions, orders, market data | 30s |
| `financial-orchestrator` | 8003 | `financial_orchestrator` | KDB + AMPS combined (Phase 2 fallback) | 90s |
| `portfolio-agent` | 8004 | `portfolio` | AMPS `portfolio_nav` topic | 60s |
| `cds-agent` | 8005 | `cds` | AMPS `cds_spreads` topic | 60s |
| `etf-agent` | 8006 | `etf` | AMPS `etf_nav` topic | 60s |
| `risk-pnl-agent` | 8007 | `risk_pnl` | AMPS `risk_metrics` topic | 90s |

All agents register themselves in DynamoDB on startup with a TTL heartbeat. If a container stops, its registry entry expires in 90 seconds.

---

## Source Structure

```
src/
  a2a/
    client.py           Single A2A HTTP call (POST /a2a)
    parallel_client.py  Concurrent fan-out — returns AgentResult per agent
    models.py           A2ATask, A2AResult Pydantic schemas
    registry.py         DynamoDB agent discovery
  agents/
    llm_router.py       LLM routing — outputs AgentConfig list (id, priority, timeout_ms)
    orchestrator.py     Entry point — routes, fans out, scores confidence, merges
    synthesizer.py      Pure-reasoning synthesis with [HIGH]/[LOW] confidence tags
    model_factory.py    LLM provider abstraction (Bedrock / Anthropic / Ollama / Mock)
    prompt_registry.py  Langfuse prompt management (self-seeding)
    demo_responses.py   Pre-scripted responses for offline demos
    kdb_agent.py        KDB specialist
    amps_agent.py       AMPS specialist
    portfolio_agent.py  Portfolio specialist
    cds_agent.py        CDS specialist
    etf_agent.py        ETF specialist
    risk_pnl_agent.py   Risk/PnL specialist
  api/
    server.py           OpenAI-compatible /v1/chat/completions endpoint
    sessions.py         DynamoDB session store
    rate_limiter.py     Daily request limits per user
  graph/
    state.py            AgentState — query, rag_context, routing_plan, confidence,
                        research, synthesis, final_response, error
    nodes.py            LangGraph nodes: intake → retrieve → orchestrate → format
    workflow.py         StateGraph compilation; run_query()
  mcp_gateway/
    gateway.py          MCP aggregation layer (port 9000)
    registry.py         DynamoDB MCP server registry (TTL 90s)
  rag/
    retriever.py        OpenSearch semantic search (SentenceTransformer)
  services/
    base_service.py     Agent FastAPI app builder — registers in DynamoDB on startup
    kdb_agent_service.py
    amps_agent_service.py
    portfolio_agent_service.py
    cds_agent_service.py
    etf_agent_service.py
    risk_pnl_agent_service.py
  config.py             All environment variable bindings
  observability.py      Langfuse + Dynatrace OTel setup
```

---

## LLM Providers

| Provider | `LLM_PROVIDER` value | Auth | When to use |
|----------|---------------------|------|-------------|
| AWS Bedrock | `bedrock` | ECS task IAM role | Production on AWS — no API key needed |
| Anthropic API | `anthropic` | `ANTHROPIC_API_KEY` | Local development |
| Ollama | `ollama` | None | Free local dev — `llama3.2:3b` |
| Mock | `mock` | None | CI / unit tests |

Bedrock model IDs (configured in `config.py` and `repo-infra/locals.tf`):
```
Synthesis:  us.anthropic.claude-sonnet-4-6-20251101-v1:0
Routing:    us.anthropic.claude-haiku-4-5-20251001-v1:0
```

Cross-region inference must be enabled in your AWS account for these model IDs.

---

## Environment Variables

### LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | `bedrock` \| `anthropic` \| `ollama` \| `mock` |
| `ANTHROPIC_API_KEY` | — | Required when `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | Main model for local Anthropic |
| `BEDROCK_MODEL` | `us.anthropic.claude-sonnet-4-6-20251101-v1:0` | Synthesis model |
| `BEDROCK_FAST_MODEL` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Routing model |

### Service identity

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_SERVICE` | `api` | Which service this container runs (`api`, `kdb`, `amps`, `portfolio`, `cds`, `etf`, `risk_pnl`) |
| `AGENT_PORT` | `8000` | Port the agent listens on |

### AWS / DynamoDB

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_DEFAULT_REGION` | `us-east-1` | AWS region |
| `AWS_ENDPOINT_URL` | — | LocalStack endpoint for local dev (`http://localstack:4566`) |
| `AGENT_REGISTRY_TABLE` | `agentic-ai-staging-agent-registry` | DynamoDB table for agent discovery |

### Agent URLs (fallback when DynamoDB is unavailable)

| Variable | Default |
|----------|---------|
| `KDB_AGENT_URL` | `http://kdb-agent:8001` |
| `AMPS_AGENT_URL` | `http://amps-agent:8002` |
| `PORTFOLIO_AGENT_URL` | `http://portfolio-agent:8004` |
| `CDS_AGENT_URL` | `http://cds-agent:8005` |
| `ETF_AGENT_URL` | `http://etf-agent:8006` |
| `RISK_PNL_AGENT_URL` | `http://risk-pnl-agent:8007` |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSERVABILITY_ENABLED` | `false` | Enable Langfuse tracing |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | — | Langfuse project secret key |
| `LANGFUSE_HOST` | `http://localhost:3000` | Langfuse server URL |

### Features

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_MODE_ENABLED` | `false` | Pre-scripted responses for demos (no LLM needed) |
| `SKIP_INGEST` | `false` | Skip RAG ingestion on startup |
| `KDB_ENABLED` | `false` | Enable KDB+ data queries |
| `AMPS_ENABLED` | `false` | Enable AMPS live data |
| `RATE_LIMIT_ENABLED` | `true` | Enable per-user daily request limits |

---

## Running Locally

See [repo-local-dev/README.md](../repo-local-dev/README.md) for Docker Compose profiles (`solo`, `demo`, `agents`, `amps`, `rag`).

To run a single agent outside Docker:

```bash
cd /path/to/monorepo
pip install -r repo-api/requirements.txt

# Start LocalStack first (for DynamoDB), then:
AGENT_SERVICE=kdb \
AGENT_PORT=8001 \
AWS_ENDPOINT_URL=http://localhost:4566 \
LLM_PROVIDER=anthropic \
ANTHROPIC_API_KEY=sk-ant-... \
python repo-api/main.py
```

---

## Running in AWS (ECS Fargate)

The Terraform in `repo-infra/` launches 8 ECS task definitions from the same Docker image:

```
agentic-ai-staging-api              AGENT_SERVICE=api,  LLM_PROVIDER=bedrock
agentic-ai-staging-kdb-agent        AGENT_SERVICE=kdb,  LLM_PROVIDER=bedrock
agentic-ai-staging-amps-agent       AGENT_SERVICE=amps, LLM_PROVIDER=bedrock
agentic-ai-staging-portfolio-agent  AGENT_SERVICE=portfolio
agentic-ai-staging-cds-agent        AGENT_SERVICE=cds
agentic-ai-staging-etf-agent        AGENT_SERVICE=etf
agentic-ai-staging-risk-pnl-agent   AGENT_SERVICE=risk_pnl
```

`LLM_PROVIDER=bedrock` is set in the task definition. The ECS task IAM role provides `bedrock:InvokeModel` — no API keys stored anywhere.

Agent-to-agent calls use AWS Cloud Map private DNS:
```
http://agentic-ai-staging-kdb-agent.staging.local:8001
http://agentic-ai-staging-portfolio-agent.staging.local:8004
```

See [repo-infra/README.md](../repo-infra/README.md) for the full deployment guide.
