# Prompt: Replicate the Agentic AI System

> Copy and paste this prompt into Claude Code to replicate the full project from scratch.

---

Build me a multi-agent financial analysis system called **agentic-ai-system**.
This is a POC for Bond trading desk analytics.

## Tech stack (non-negotiable)

- **LangGraph** as the deterministic control plane (graph structure, RAG pipeline, API)
- **Strands** (AWS multi-agent framework) as the non-deterministic data plane (agents)
- **MCP** (Model Context Protocol) for all external tool integrations
- **FastAPI** OpenAI-compatible REST API (port 8000)
- **ChromaDB** + `all-MiniLM-L6-v2` for local RAG
- **DuckDB** reading Parquet for the KDB POC (no KDB+ license needed)
- **AMPS** (60East Technologies) for live pub/sub data (optional, via Docker)
- **Amazon Bedrock** for production LLM (local dev uses Anthropic API via LiteLLM)
- **Terraform** (hashicorp/aws ~> 5.0, hashicorp/random ~> 3.6) for infrastructure

Read `prompts/replication_guide.md` in this repo FIRST — it contains every
architectural decision, file layout, and implementation detail.
Follow it exactly.

## What to build

Follow the project structure in `replication_guide.md` section 3.
Build in this order:
1. `src/config.py` — all env vars
2. `src/graph/` — LangGraph state, nodes, workflow
3. `src/rag/retriever.py` — ChromaDB setup
4. `src/mcp_server/kdb_mcp_server.py` — 5 KDB tools (DuckDB backend)
5. `src/mcp_server/amps_mcp_server.py` — 5 AMPS tools (HTTP admin + TCP client)
6. `src/mcp_clients.py` — MCP client factories + context managers
7. `src/agents/model_factory.py` — tiered model strategy (Sonnet + Haiku)
8. `src/agents/kdb_agent.py` — KDB specialist (Haiku)
9. `src/agents/amps_agent.py` — AMPS specialist (Haiku)
10. `src/agents/financial_orchestrator.py` — Financial orchestrator (Sonnet, agent-as-tool)
11. `src/agents/orchestrator.py` — Top-level routing (keyword-based, no extra LLM call)
12. `src/agents/researcher.py` + `synthesizer.py` — General pipeline
13. `src/agents/tools.py` — Shared Strands tools (RAG search, summarize)
14. `src/api/server.py` — FastAPI OpenAI-compatible endpoint
15. `src/observability.py` — Dual Langfuse + Phoenix tracing
16. `scripts/generate_synthetic_rfq.py` — Bond RFQ parquet generator
17. `scripts/ingest_docs.py` + `ingest_amps_docs.py` — RAG ingestion
18. `scripts/amps_publisher.py` — AMPS live data simulator
19. `main.py` — CLI entry point
20. `Dockerfile` + `docker/entrypoint.sh` — Production container
21. `docker-compose.*.yml` — AMPS, KDB, observability services
22. `infra/` — Terraform: main.tf, variables.tf, locals.tf, outputs.tf, networking.tf, vpc_endpoints.tf, ecr.tf, iam.tf, data.tf, ecs.tf, alb.tf, autoscaling.tf, terraform.tfvars.example
23. `.env.example`, `requirements.txt`, `.gitignore`

## Critical constraints

1. Keyword routing — NO extra LLM call for routing. Use `_FINANCIAL_KEYWORDS` set.
2. Tiered models — Sonnet for orchestrators, Haiku for sub-agents.
3. Agent-as-tool — KDB and AMPS agents are @tool functions in the Financial Orchestrator.
4. MCP stdio — all custom MCP servers run as Python subprocesses via stdio transport.
5. Proactive agents — add "CRITICAL: Be proactive" section to all orchestrator system prompts.
6. Feature flags — AMPS_ENABLED, KDB_ENABLED, OBSERVABILITY_ENABLED all default false.
7. AMPS publish API — `client.publish(topic_str, json_str)` — two strings, no Message object.
8. Bedrock model IDs — use cross-region inference profiles: `us.anthropic.claude-*`

## Reference data

The synthetic dataset uses these traders and bonds (use exact same IDs so KDB and AMPS data can be correlated):

Traders (12): T_HY_001..T_HY_005 (HY desk), T_IG_001..T_IG_003 (IG desk),
              T_EM_001..T_EM_002 (EM desk), T_RATES_001..T_RATES_002 (RATES desk)

Bonds (12 ISINs):
- HY: US345370CY87 (Ford 8.5%), US92336GAN41 (Verizon 7%), US38141GXG96 (GS 6.75%),
      US037833DV79 (Apple 5.25%), US594918BW80 (MSFT 4.75%)
- IG: US166764BG78 (Chevron 3.5%), US931142EK26 (Walmart 2.85%), US037833AK68 (Apple 2.4%)
- EM: US105756BQ96 (Brazil 5.625%), US4MEXSOV001 (Mexico 4.75%)
- RATES: US912797HS68 (UST 4.25%), US912810TM57 (UST 4.5%)

AMPS topics: `positions` (key: /id), `orders` (key: /order_id), `market-data` (key: /symbol)
AMPS ports: 8085 (HTTP admin, /amps.json), 9007 (TCP JSON transport)
