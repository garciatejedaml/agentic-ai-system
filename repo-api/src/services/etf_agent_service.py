"""
ETF Agent Service (Phase 3 — A2A)

Runs the ETF Analytics Agent as an independent HTTP service.
Exposes the Google A2A protocol endpoints:
  GET  /.well-known/agent.json
  POST /a2a
  GET  /health

Port: 8006 (default)

Run locally:
  uvicorn src.services.etf_agent_service:app --port 8006

In Docker Compose: started by phase3_entrypoint.sh with AGENT_SERVICE=etf
"""
import os

from src.a2a.models import AgentSkill
from src.agents.etf_agent import run_etf_agent
from src.services.base_service import create_agent_app

_ENDPOINT = os.getenv(
    "ETF_AGENT_ENDPOINT",
    f"http://etf-agent:{os.getenv('AGENT_PORT', '8006')}",
)

app = create_agent_app(
    agent_id="etf-agent",
    name="ETF Analytics Agent",
    description=(
        "Specialist agent for fixed income ETF analytics. "
        "Covers 15 ETFs (HYG, JNK, LQD, EMB, TLT, AGG, and more). "
        "Use for NAV, AUM, premium/discount, creation/redemption flows, and basket composition."
    ),
    endpoint=_ENDPOINT,
    skills=[
        AgentSkill(
            id="etf_nav_aum",
            name="ETF NAV and AUM",
            description="NAV, market price, premium/discount to NAV, assets under management",
        ),
        AgentSkill(
            id="etf_flows",
            name="ETF Flows",
            description="Weekly creation/redemption flow history — inflows vs outflows",
        ),
        AgentSkill(
            id="etf_basket",
            name="ETF Basket Composition",
            description="Top holdings by weight, sector and rating breakdown",
        ),
    ],
    desk_names=["HY", "IG", "EM", "RATES"],
    handle_task=run_etf_agent,
)
