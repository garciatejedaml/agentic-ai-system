# repo-api — Agentic AI System API

FastAPI server + LangGraph workflow + Strands specialist agents + RAG retrieval.

## Structure

```
src/
  agents/        ← Strands AI agents (KDB, AMPS, Financial Orchestrator, Researcher)
  api/           ← FastAPI endpoints + session store
  graph/         ← LangGraph workflow (intake → retrieve → strands → format)
  rag/           ← ChromaDB retriever
  config.py      ← Config from env vars (supports Anthropic + AWS Bedrock)
  mcp_clients.py ← MCP client factory (Brave, Fetch, Filesystem, AMPS, KDB)
  observability.py ← Langfuse tracing setup
main.py          ← CLI entry point
requirements.txt
Dockerfile       ← Build from monorepo root: docker build -f repo-api/Dockerfile .
```

## Local dev

```bash
cp .env.example .env  # fill in ANTHROPIC_API_KEY etc.
pip install -r requirements.txt
python main.py "Who are the top HY traders?"
# or start the API:
uvicorn src.api.server:app --reload
```

## Docker (monorepo build context)

```bash
# Run from the monorepo root
docker build -f repo-api/Dockerfile -t agentic-ai-system:latest .
docker run -p 8000:8000 -e LLM_PROVIDER=anthropic -e ANTHROPIC_API_KEY=sk-ant-... agentic-ai-system:latest
```

## Dependencies on other repos

| Dependency | Location | How used |
|---|---|---|
| MCP servers | `repo-mcp-tools/` | Subprocess via stdio (auto-copied to `src/mcp_server/` in Docker) |
| RAG data | `repo-rag-ingest/data/` | Ingested into ChromaDB on container start |
| Ingest scripts | `repo-rag-ingest/scripts/` | Run by `docker/entrypoint.sh` on cold start |
