#!/bin/bash
# ── Phase 2 Service Selector Entrypoint ───────────────────────────────────────
# Selects which A2A agent service to start based on $AGENT_SERVICE env var.
# All services share the same Docker image — the env var picks the role.
#
# Usage (Docker Compose):
#   environment:
#     AGENT_SERVICE: kdb           → KDB Agent HTTP service (:8001)
#     AGENT_SERVICE: amps          → AMPS Agent HTTP service (:8002)
#     AGENT_SERVICE: financial_orchestrator → Financial Orchestrator (:8003)
#     AGENT_SERVICE: api (default) → API gateway (original entrypoint.sh)
#
# Environment variables:
#   AGENT_SERVICE  — which service to start (default: api)
#   AGENT_PORT     — port override (default per service)
#   WORKERS        — uvicorn worker count (default: 1)

set -e

AGENT_SERVICE="${AGENT_SERVICE:-api}"
WORKERS="${WORKERS:-1}"

echo "[phase2-entrypoint] Starting service: ${AGENT_SERVICE}"

case "$AGENT_SERVICE" in
  kdb)
    PORT="${AGENT_PORT:-8001}"
    exec uvicorn src.services.kdb_agent_service:app \
      --host 0.0.0.0 \
      --port "$PORT" \
      --workers "$WORKERS"
    ;;

  amps)
    PORT="${AGENT_PORT:-8002}"
    exec uvicorn src.services.amps_agent_service:app \
      --host 0.0.0.0 \
      --port "$PORT" \
      --workers "$WORKERS"
    ;;

  financial_orchestrator)
    PORT="${AGENT_PORT:-8003}"
    exec uvicorn src.services.financial_orchestrator_service:app \
      --host 0.0.0.0 \
      --port "$PORT" \
      --workers "$WORKERS"
    ;;

  api|*)
    # Default: original Phase 1 entrypoint (RAG ingest + uvicorn on :8000)
    exec /entrypoint.sh
    ;;
esac
