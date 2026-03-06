# repo-api — Agentic AI System API

FastAPI server + LangGraph workflow + Strands specialist agents + RAG retrieval.
Phase 2 adds A2A (Agent-to-Agent) services for distributed multi-agent execution.

## Structure

```
src/
  a2a/           ← Phase 2: A2A protocol models, registry client, HTTP client
  agents/        ← Strands AI agents (KDB, AMPS, Financial Orchestrator v1+v2, Researcher)
  api/           ← FastAPI endpoints + DynamoDB session store (500 users)
  graph/         ← LangGraph workflow (intake → retrieve → strands → format)
  rag/           ← ChromaDB retriever
  services/      ← Phase 2: A2A FastAPI apps (kdb, amps, financial-orchestrator)
  config.py      ← Config from env vars (supports Anthropic + AWS Bedrock)
  mcp_clients.py ← MCP client factory (Brave, Fetch, Filesystem, AMPS, KDB)
  observability.py ← Langfuse tracing setup
main.py          ← CLI entry point
requirements.txt
docker/
  entrypoint.sh         ← Phase 1: API + ingest startup
  phase2_entrypoint.sh  ← Phase 2: selects service via AGENT_SERVICE env var
Dockerfile       ← Build from monorepo root: docker build -f repo-api/Dockerfile .
```

## Local dev (Phase 1 — monolith)

```bash
cp .env.example .env  # fill in ANTHROPIC_API_KEY etc.
pip install -r requirements.txt
python main.py "Who are the top HY traders?"
# or start the API:
uvicorn src.api.server:app --reload
```

## Local dev (Phase 2 — A2A multi-agent)

```bash
# From monorepo root: build image then start all services
docker build -f repo-api/Dockerfile -t agentic-ai-system:phase2 .
docker compose -f repo-local-dev/docker-compose.phase2.yml up -d

# Verify agent cards
curl http://localhost:8001/.well-known/agent.json
curl http://localhost:8002/.well-known/agent.json
curl http://localhost:8003/.well-known/agent.json

# End-to-end test
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Who are the top HY traders?"}]}'
```

## Dependencies on other repos

| Dependency | Location | How used |
|---|---|---|
| MCP servers | `repo-mcp-tools/` | Subprocess via stdio (auto-copied to `src/mcp_server/` in Docker) |
| RAG data | `repo-rag-ingest/data/` | Ingested into ChromaDB on container start |
| Ingest scripts | `repo-rag-ingest/scripts/` | Run by `docker/entrypoint.sh` on cold start |
| Local dev env | `repo-local-dev/` | Docker Compose stacks for running everything locally |
