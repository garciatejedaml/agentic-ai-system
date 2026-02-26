"""
CDS Agent Service (Phase 3 — A2A)

Runs the CDS Market Data Agent as an independent HTTP service.
Exposes the Google A2A protocol endpoints:
  GET  /.well-known/agent.json
  POST /a2a
  GET  /health

Port: 8005 (default)

Run locally:
  uvicorn src.services.cds_agent_service:app --port 8005

In Docker Compose: started by phase3_entrypoint.sh with AGENT_SERVICE=cds
"""
import os

from src.a2a.models import AgentSkill
from src.agents.cds_agent import run_cds_agent
from src.services.base_service import create_agent_app

_ENDPOINT = os.getenv(
    "CDS_AGENT_ENDPOINT",
    f"http://cds-agent:{os.getenv('AGENT_PORT', '8005')}",
)

app = create_agent_app(
    agent_id="cds-agent",
    name="CDS Market Data Agent",
    description=(
        "Specialist agent for Credit Default Swap market data. "
        "Covers ~50 reference entities across HY, IG, and EM with 1/3/5/7/10y tenor spreads. "
        "Use for CDS spread levels, term structure analysis, and credit screener."
    ),
    endpoint=_ENDPOINT,
    skills=[
        AgentSkill(
            id="cds_spreads",
            name="CDS Spreads",
            description="CDS spread levels for specific entities and tenors",
        ),
        AgentSkill(
            id="cds_term_structure",
            name="CDS Term Structure",
            description="Full credit curve (1/3/5/7/10y) for a reference entity",
        ),
        AgentSkill(
            id="cds_screener",
            name="CDS Screener",
            description="Filter entities by spread range, sector, or rating",
        ),
    ],
    desk_names=["HY", "IG", "EM"],
    handle_task=run_cds_agent,
)
