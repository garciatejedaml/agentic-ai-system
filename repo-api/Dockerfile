# ── Agentic AI System — Main Application Image ────────────────────────────────
#
# Contains: LangGraph API (FastAPI) + Strands Financial Orchestrator
#           + all specialist agents + MCP servers (stdio subprocess mode)
#
# Runs on: ECS Fargate (linux/amd64) in AWS
# Listens: port 8000 (OpenAI-compatible REST API)
#
# AMPS and KDB integrations are optional at runtime via env vars:
#   AMPS_ENABLED=true  →  needs AMPS MCP server reachable (add as sidecar or use HTTP transport)
#   KDB_ENABLED=true   →  KDB_MODE=poc uses the parquet data bundled in the image
#
# Build (run from the monorepo root — build context must include all sub-repos):
#   docker build -f repo-api/Dockerfile -t agentic-ai-system:latest .
#
# In a real multi-repo CI/CD setup this Dockerfile would be replaced by a
# pipeline that pulls each repo separately before building.
#
# Run locally:
#   docker run -p 8000:8000 \
#     -e LLM_PROVIDER=bedrock \
#     -e AWS_DEFAULT_REGION=us-east-1 \
#     agentic-ai-system:latest
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# System dependencies: curl (healthcheck), Node.js (MCP npm servers), uvx (mcp-fetch)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# Install uvx (uv tool runner) for mcp-server-fetch
RUN pip install --no-cache-dir uv

WORKDIR /app

# ── Python dependencies ────────────────────────────────────────────────────────
# Build context = monorepo root; reference sub-repo paths
COPY repo-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install AMPS Python client from local zip if present (optional)
# The zip is not in PyPI; it ships with the AMPS binary download.
# If building without AMPS, this step is safely skipped.
COPY repo-rag-ingest/amps/client/ /tmp/amps-client/
RUN if ls /tmp/amps-client/*.zip 2>/dev/null; then \
        pip install --no-cache-dir /tmp/amps-client/*.zip; \
    else \
        echo "AMPS client zip not found — AMPS integration will be unavailable"; \
    fi

# ── Application source ────────────────────────────────────────────────────────
# API code from repo-api
COPY repo-api/src/ ./src/
# MCP servers from repo-mcp-tools, placed at src/mcp_server/ (matches MCP_SERVER_DIR)
COPY repo-mcp-tools/ ./src/mcp_server/
# Ingestion scripts and training data from repo-rag-ingest
COPY repo-rag-ingest/scripts/ ./scripts/
COPY repo-rag-ingest/data/ ./data/
COPY repo-api/main.py .

# Create directory for ChromaDB persistence
# In production: mount an EFS volume here or switch to Aurora pgvector
RUN mkdir -p /data/chroma_db

# ── Runtime configuration ──────────────────────────────────────────────────────
# MCP_SERVER_DIR tells mcp_clients.py where to find the MCP server scripts in-container
ENV MCP_SERVER_DIR=/app/src/mcp_server \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    # Default to Bedrock in production; override with LLM_PROVIDER=anthropic for local testing
    LLM_PROVIDER=bedrock \
    # RAG settings
    CHROMA_PERSIST_DIR=/data/chroma_db \
    KDB_DATA_PATH=/app/data/kdb \
    # Observability off by default (enable via env in ECS task definition)
    OBSERVABILITY_ENABLED=false

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Pre-warm: run ingest on startup if ChromaDB is empty
# Uses the CMD entrypoint script to ensure RAG is ready before serving
COPY repo-api/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
