#!/bin/bash
# ── Phase 3 Service Selector Entrypoint ───────────────────────────────────────
# Extends Phase 2 with 4 new specialist agents (portfolio, cds, etf, risk_pnl).
# Selects which A2A agent service to start based on $AGENT_SERVICE env var.
# All services share the same Docker image — the env var picks the role.
#
# Usage (Docker Compose):
#   environment:
#     AGENT_SERVICE: kdb                 → KDB Agent HTTP service (:8001)
#     AGENT_SERVICE: amps                → AMPS Agent HTTP service (:8002)
#     AGENT_SERVICE: financial_orchestrator → Financial Orchestrator (:8003)
#     AGENT_SERVICE: portfolio           → Portfolio Holdings Agent (:8004)
#     AGENT_SERVICE: cds                 → CDS Market Data Agent (:8005)
#     AGENT_SERVICE: etf                 → ETF Analytics Agent (:8006)
#     AGENT_SERVICE: risk_pnl            → Risk & P&L Agent (:8007)
#     AGENT_SERVICE: api (default)       → API gateway (entrypoint.sh)
#
# Environment variables:
#   AGENT_SERVICE  — which service to start (default: api)
#   AGENT_PORT     — port override (default per service)
#   WORKERS        — uvicorn worker count (default: 1)

set -e

AGENT_SERVICE="${AGENT_SERVICE:-api}"
WORKERS="${WORKERS:-1}"

echo "[phase3-entrypoint] Starting service: ${AGENT_SERVICE}"

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

  portfolio)
    PORT="${AGENT_PORT:-8004}"
    exec uvicorn src.services.portfolio_agent_service:app \
      --host 0.0.0.0 \
      --port "$PORT" \
      --workers "$WORKERS"
    ;;

  cds)
    PORT="${AGENT_PORT:-8005}"
    exec uvicorn src.services.cds_agent_service:app \
      --host 0.0.0.0 \
      --port "$PORT" \
      --workers "$WORKERS"
    ;;

  etf)
    PORT="${AGENT_PORT:-8006}"
    exec uvicorn src.services.etf_agent_service:app \
      --host 0.0.0.0 \
      --port "$PORT" \
      --workers "$WORKERS"
    ;;

  risk_pnl)
    PORT="${AGENT_PORT:-8007}"
    exec uvicorn src.services.risk_pnl_agent_service:app \
      --host 0.0.0.0 \
      --port "$PORT" \
      --workers "$WORKERS"
    ;;

  api|*)
    # Default: original Phase 1 entrypoint (RAG ingest + uvicorn on :8000)
    exec /entrypoint.sh
    ;;
esac
