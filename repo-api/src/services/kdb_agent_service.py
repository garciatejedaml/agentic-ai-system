"""
KDB Agent Service (Phase 2 — A2A)

Runs the KDB Historical Data Agent as an independent HTTP service.
Exposes the Google A2A protocol endpoints:
  GET  /.well-known/agent.json
  POST /a2a
  GET  /health

Port: 8001 (default)

Run locally:
  uvicorn src.services.kdb_agent_service:app --port 8001

In Docker Compose: started by phase2_entrypoint.sh with AGENT_SERVICE=kdb
"""
import os

from src.a2a.models import AgentSkill
from src.agents.kdb_agent import run_kdb_agent
from src.services.base_service import create_agent_app

_ENDPOINT = os.getenv("KDB_AGENT_ENDPOINT", f"http://kdb-agent:{os.getenv('AGENT_PORT', '8001')}")

app = create_agent_app(
    agent_id="kdb-agent",
    name="KDB Historical Data Agent",
    description=(
        "Specialist agent for Bond RFQ historical analytics. "
        "Queries 6+ months of trading data across HY, IG, EM, and RATES desks. "
        "Use for trader rankings, hit rates, spread analysis, and notional trends."
    ),
    endpoint=_ENDPOINT,
    skills=[
        AgentSkill(
            id="bond_analytics",
            name="Bond RFQ Analytics",
            description="Aggregated analytics over historical Bond RFQ records",
        ),
        AgentSkill(
            id="trader_performance",
            name="Trader Performance",
            description="Hit rate, spread, and win/loss rankings per trader",
        ),
        AgentSkill(
            id="rfq_history",
            name="RFQ History",
            description="Custom SQL queries over the bond_rfq table",
        ),
    ],
    desk_names=["HY", "IG", "EM", "RATES"],
    handle_task=run_kdb_agent,
)
