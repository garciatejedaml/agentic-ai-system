"""
Risk & P&L Agent Service (Phase 3 — A2A)

Runs the Risk & P&L cross-cutting agent as an independent HTTP service.
Exposes the Google A2A protocol endpoints:
  GET  /.well-known/agent.json
  POST /a2a
  GET  /health

Port: 8007 (default)

This agent makes internal A2A sub-calls to:
  portfolio-agent (port 8004) — for holdings
  kdb-agent (port 8001)      — for historical spread data

Run locally:
  uvicorn src.services.risk_pnl_agent_service:app --port 8007

In Docker Compose: started by phase3_entrypoint.sh with AGENT_SERVICE=risk_pnl
"""
import os

from src.a2a.models import AgentSkill
from src.agents.risk_pnl_agent import run_risk_pnl_agent
from src.services.base_service import create_agent_app

_ENDPOINT = os.getenv(
    "RISK_PNL_AGENT_ENDPOINT",
    f"http://risk-pnl-agent:{os.getenv('AGENT_PORT', '8007')}",
)

app = create_agent_app(
    agent_id="risk-pnl-agent",
    name="Risk & P&L Agent",
    description=(
        "Cross-cutting risk and P&L analytics agent. "
        "Computes VaR (95%/99%), DV01, CS01 from live portfolio positions + historical spreads. "
        "Provides P&L attribution by desk and trader. "
        "Internally calls portfolio-agent and kdb-agent for data, then computes metrics in-process."
    ),
    endpoint=_ENDPOINT,
    skills=[
        AgentSkill(
            id="var_computation",
            name="VaR Computation",
            description="Historical simulation VaR at 95% and 99% confidence, 1-day horizon",
        ),
        AgentSkill(
            id="dv01_cs01",
            name="DV01 and CS01",
            description="Dollar value of 1bp rate move (DV01) and spread move (CS01) per portfolio",
        ),
        AgentSkill(
            id="pnl_attribution",
            name="P&L Attribution",
            description="P&L breakdown by desk and trader from historical RFQ data",
        ),
    ],
    desk_names=["HY", "IG", "EM", "RATES"],
    handle_task=run_risk_pnl_agent,
)
