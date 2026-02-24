"""
AMPS Agent Service (Phase 2 — A2A)

Runs the AMPS Real-Time Data Agent as an independent HTTP service.
Exposes the Google A2A protocol endpoints:
  GET  /.well-known/agent.json
  POST /a2a
  GET  /health

Port: 8002 (default)

Run locally:
  uvicorn src.services.amps_agent_service:app --port 8002

In Docker Compose: started by phase2_entrypoint.sh with AGENT_SERVICE=amps
"""
import os

from src.a2a.models import AgentSkill
from src.agents.amps_agent import run_amps_agent
from src.services.base_service import create_agent_app

_ENDPOINT = os.getenv("AMPS_AGENT_ENDPOINT", f"http://amps-agent:{os.getenv('AGENT_PORT', '8002')}")

app = create_agent_app(
    agent_id="amps-agent",
    name="AMPS Real-Time Data Agent",
    description=(
        "Specialist agent for live pub/sub data from AMPS (60East Technologies). "
        "Queries current state-of-world: today's orders, live positions, market quotes. "
        "Use for intraday, real-time, and 'right now' queries."
    ),
    endpoint=_ENDPOINT,
    skills=[
        AgentSkill(
            id="realtime_positions",
            name="Live Positions",
            description="Current open positions from AMPS SOW",
        ),
        AgentSkill(
            id="live_orders",
            name="Live Orders",
            description="Today's active orders and intraday order flow",
        ),
        AgentSkill(
            id="market_data",
            name="Market Data",
            description="Live bid/ask quotes and market-data topic",
        ),
    ],
    desk_names=["HY", "IG", "EM", "RATES"],
    handle_task=run_amps_agent,
)
