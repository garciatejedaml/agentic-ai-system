"""
A2A Protocol Models (Google Agent-to-Agent Protocol)

Pydantic models for the A2A HTTP protocol used for inter-agent communication.
Each agent exposes:
  GET  /.well-known/agent.json  → AgentCard
  POST /a2a                     → A2ATask → A2AResult
  GET  /health                  → HealthResponse

Reference: https://google.github.io/A2A/
"""
from typing import Literal

from pydantic import BaseModel


# ── Agent Card ────────────────────────────────────────────────────────────────

class AgentSkill(BaseModel):
    id: str
    name: str
    description: str


class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    capabilities: AgentCapabilities = AgentCapabilities()
    skills: list[AgentSkill] = []


# ── Task Request ──────────────────────────────────────────────────────────────

class MessagePart(BaseModel):
    text: str


class TaskMessage(BaseModel):
    role: str = "user"
    parts: list[MessagePart]


class A2ATask(BaseModel):
    id: str
    message: TaskMessage
    sessionId: str = ""


# ── Task Result ───────────────────────────────────────────────────────────────

class ArtifactPart(BaseModel):
    text: str


class Artifact(BaseModel):
    parts: list[ArtifactPart]


class A2AResult(BaseModel):
    id: str
    status: Literal["completed", "failed"] = "completed"
    artifacts: list[Artifact] = []
    error: str | None = None


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    agent_id: str
    endpoint: str
