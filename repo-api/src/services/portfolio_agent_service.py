"""
Portfolio Agent Service (Phase 3 — A2A)

Runs the Portfolio Holdings Agent as an independent HTTP service.
Exposes the Google A2A protocol endpoints:
  GET  /.well-known/agent.json
  POST /a2a
  GET  /health

Port: 8004 (default)

Run locally:
  uvicorn src.services.portfolio_agent_service:app --port 8004

In Docker Compose: started by phase3_entrypoint.sh with AGENT_SERVICE=portfolio
"""
import os

from src.a2a.models import AgentSkill
from src.agents.portfolio_agent import run_portfolio_agent
from src.services.base_service import create_agent_app

_ENDPOINT = os.getenv(
    "PORTFOLIO_AGENT_ENDPOINT",
    f"http://portfolio-agent:{os.getenv('AGENT_PORT', '8004')}",
)

app = create_agent_app(
    agent_id="portfolio-agent",
    name="Portfolio Holdings Agent",
    description=(
        "Specialist agent for portfolio holdings and exposure analytics. "
        "Covers 5 fixed income portfolios: HY_MAIN, IG_CORE, EM_BLEND, RATES_GOV, MULTI_STRAT. "
        "Use for position weights, sector exposure, concentration analysis, and duration/spread profiles."
    ),
    endpoint=_ENDPOINT,
    skills=[
        AgentSkill(
            id="portfolio_holdings",
            name="Portfolio Holdings",
            description="Full position list with ISIN, issuer, market value, weight, duration, spread",
        ),
        AgentSkill(
            id="portfolio_exposure",
            name="Portfolio Exposure",
            description="Sector-level aggregated exposure with market value weights",
        ),
        AgentSkill(
            id="portfolio_concentration",
            name="Concentration Risk",
            description="Top N positions by market value, concentration % of NAV",
        ),
    ],
    desk_names=["HY", "IG", "EM", "RATES", "MULTI"],
    handle_task=run_portfolio_agent,
)
