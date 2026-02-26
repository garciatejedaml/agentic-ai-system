#!/bin/bash
# ── Container entrypoint ───────────────────────────────────────────────────────
# 1. Wait for OpenSearch to be ready
# 2. Ingest docs into OpenSearch if the index is empty (idempotent)
# 3. Start the FastAPI server
set -e

echo "[entrypoint] Starting Agentic AI System..."

# Wait for OpenSearch to accept connections (up to 60s)
OPENSEARCH_URL="${OPENSEARCH_URL:-http://opensearch:9200}"
if [ "${SKIP_INGEST:-false}" != "true" ]; then
    echo "[entrypoint] Waiting for OpenSearch at ${OPENSEARCH_URL}..."
    for i in $(seq 1 30); do
        if curl -sf "${OPENSEARCH_URL}/_cluster/health" -o /dev/null 2>&1; then
            echo "[entrypoint] OpenSearch is ready (attempt ${i})."
            break
        fi
        echo "[entrypoint] Waiting... (${i}/30)"
        sleep 2
    done
fi

# Ingest docs (idempotent — sha256-keyed, safe to re-run)
if [ "${SKIP_INGEST:-false}" != "true" ]; then
    echo "[entrypoint] Running doc ingestion (set SKIP_INGEST=true to skip)..."
    python scripts/ingest_docs.py          || echo "[entrypoint] Warning: ingest_docs.py failed (non-fatal)"
    python scripts/ingest_amps_docs.py     || echo "[entrypoint] Warning: ingest_amps_docs.py failed (non-fatal)"
    python scripts/ingest_amps_schemas.py  || echo "[entrypoint] Warning: ingest_amps_schemas.py failed (non-fatal)"
fi

echo "[entrypoint] Starting API server on port ${PORT:-8000}..."
exec uvicorn src.api.server:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${UVICORN_WORKERS:-2}" \
    --log-level "${LOG_LEVEL:-info}"
