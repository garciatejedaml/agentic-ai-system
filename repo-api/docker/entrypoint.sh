#!/bin/bash
# ── Container entrypoint ───────────────────────────────────────────────────────
# 1. Ingest docs into ChromaDB if the collection is empty (idempotent)
# 2. Start the FastAPI server
set -e

echo "[entrypoint] Starting Agentic AI System..."

# Ingest docs only if ChromaDB collection does not exist yet
# The ingest scripts are idempotent (they check before inserting)
if [ "${SKIP_INGEST:-false}" != "true" ]; then
    echo "[entrypoint] Running doc ingestion (set SKIP_INGEST=true to skip)..."
    python scripts/ingest_docs.py      || echo "[entrypoint] Warning: ingest_docs.py failed (non-fatal)"
    python scripts/ingest_amps_docs.py || echo "[entrypoint] Warning: ingest_amps_docs.py failed (non-fatal)"
fi

echo "[entrypoint] Starting API server on port ${PORT:-8000}..."
exec uvicorn src.api.server:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${UVICORN_WORKERS:-2}" \
    --log-level "${LOG_LEVEL:-info}"
