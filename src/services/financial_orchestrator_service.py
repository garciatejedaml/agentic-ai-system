"""
Financial Orchestrator Service (Phase 2 — A2A)

Runs the Financial Orchestrator as an independent HTTP service.
It receives queries from the API service and dispatches sub-tasks
to KDB Agent and AMPS Agent via A2A HTTP calls.

Exposes:
  GET  /.well-known/agent.json
  POST /a2a
  GET  /health

Port: 8003 (default)

Run locally:
  uvicorn src.services.financial_orchestrator_service:app --port 8003

In Docker Compose: started by phase2_entrypoint.sh with AGENT_SERVICE=financial_orchestrator
"""
import os

from src.a2a.models import AgentSkill
from src.agents.financial_orchestrator_v2 import run_financial_orchestrator_v2
from src.services.base_service import create_agent_app

_ENDPOINT = os.getenv(
    "FINANCIAL_ORCHESTRATOR_ENDPOINT",
    f"http://financial-orchestrator:{os.getenv('AGENT_PORT', '8003')}",
)

app = create_agent_app(
    agent_id="financial-orchestrator",
    name="Financial Orchestrator",
    description=(
        "Senior Bond Trading Analyst. Coordinates KDB historical data, "
        "AMPS real-time data, and domain knowledge to answer complex "
        "financial queries across HY, IG, EM, and RATES desks."
    ),
    endpoint=_ENDPOINT,
    skills=[
        AgentSkill(
            id="financial_analysis",
            name="Financial Analysis",
            description="Multi-source bond trading analytics combining historical and live data",
        ),
        AgentSkill(
            id="bond_trading",
            name="Bond Trading Insights",
            description="Trader performance, desk strategy, and market context",
        ),
        AgentSkill(
            id="multi_source",
            name="Multi-Source Synthesis",
            description="Combines KDB, AMPS, and knowledge base into unified analysis",
        ),
    ],
    desk_names=["HY", "IG", "EM", "RATES"],
    handle_task=run_financial_orchestrator_v2,
)
