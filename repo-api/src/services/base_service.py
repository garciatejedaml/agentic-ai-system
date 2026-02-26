"""
Base Agent Service

Shared FastAPI application factory used by all A2A agent services.
Each specialist agent (KDB, AMPS, Financial Orchestrator) calls
`create_agent_app()` to get a pre-configured FastAPI app with:

  GET  /health                   → HealthResponse
  GET  /.well-known/agent.json   → AgentCard
  POST /a2a                      → A2AResult

The agent registers in DynamoDB on startup and deregisters on shutdown.

Usage:
    app = create_agent_app(
        agent_id="kdb-agent",
        name="KDB Historical Agent",
        description="Bond RFQ historical analytics",
        endpoint="http://kdb-agent:8001",
        skills=[AgentSkill(id="bond_analytics", name="Bond Analytics", description="...")],
        desk_names=["HY", "IG", "EM", "RATES"],
        handle_task=run_kdb_agent,
    )
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from src.a2a.models import (
    A2AResult,
    A2ATask,
    Artifact,
    ArtifactPart,
    AgentCard,
    AgentSkill,
    AgentCapabilities,
    HealthResponse,
)
from src.a2a.registry import deregister_agent, register_agent
from src.observability import setup_observability


def create_agent_app(
    agent_id: str,
    name: str,
    description: str,
    endpoint: str,
    skills: list[AgentSkill],
    desk_names: list[str],
    handle_task: callable,
) -> FastAPI:
    """
    Build and return a FastAPI app for an A2A agent service.

    Args:
        agent_id:    Unique ID used in DynamoDB registry (e.g. "kdb-agent")
        name:        Human-readable agent name
        description: Short description for the Agent Card
        endpoint:    Public base URL of this service (e.g. "http://kdb-agent:8001")
        skills:      List of AgentSkill objects describing capabilities
        desk_names:  Trading desks served (used for DynamoDB GSI ByDesk)
        handle_task: Synchronous callable(query: str) -> str
                     The actual agent logic (e.g. run_kdb_agent)
    """
    capabilities = [s.id for s in skills]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator:
        setup_observability()
        # Graceful startup: DynamoDB may not be ready immediately.
        # The /health endpoint renews the TTL on each call, so eventual
        # registration is guaranteed once the registry becomes available.
        try:
            register_agent(agent_id, endpoint, capabilities, desk_names)
            print(f"[{agent_id}] Registered at {endpoint}")
        except Exception as e:
            print(f"[{agent_id}] Warning: DynamoDB registration failed (will retry via /health): {e}")
        yield
        try:
            deregister_agent(agent_id)
            print(f"[{agent_id}] Deregistered")
        except Exception as e:
            print(f"[{agent_id}] Warning: DynamoDB deregistration failed: {e}")

    app = FastAPI(title=name, version="1.0.0", lifespan=lifespan)

    agent_card = AgentCard(
        name=name,
        description=description,
        url=endpoint,
        capabilities=AgentCapabilities(),
        skills=skills,
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        # Renew TTL in registry on each healthcheck
        register_agent(agent_id, endpoint, capabilities, desk_names)
        return HealthResponse(agent_id=agent_id, endpoint=endpoint)

    @app.get("/.well-known/agent.json", response_model=AgentCard)
    async def agent_json() -> AgentCard:
        return agent_card

    @app.post("/a2a", response_model=A2AResult)
    async def a2a(task: A2ATask) -> A2AResult:
        if not task.message.parts:
            raise HTTPException(status_code=400, detail="Task message has no parts")

        query = task.message.parts[0].text
        try:
            result_text = handle_task(query)
            return A2AResult(
                id=task.id,
                status="completed",
                artifacts=[Artifact(parts=[ArtifactPart(text=result_text)])],
            )
        except Exception as e:
            return A2AResult(
                id=task.id,
                status="failed",
                error=str(e),
            )

    return app
