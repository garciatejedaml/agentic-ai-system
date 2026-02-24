"""
A2A HTTP Client

Sends tasks to remote agent services using the Google A2A protocol.
Used by the Financial Orchestrator to call KDB Agent and AMPS Agent
as independent HTTP services instead of in-process function calls.

Protocol:
  POST {endpoint}/a2a
  Body: A2ATask JSON
  Response: A2AResult JSON
"""
import asyncio
import uuid

import httpx

from src.a2a.models import A2AResult, A2ATask, Artifact, ArtifactPart, TaskMessage, MessagePart


async def call_agent(
    endpoint: str,
    query: str,
    timeout: int = 120,
    session_id: str = "",
) -> str:
    """
    Send a task to an A2A agent service and return the text result.

    Args:
        endpoint:   Base URL of the agent (e.g. "http://kdb-agent:8001")
        query:      Natural language query to send
        timeout:    Max seconds to wait for response
        session_id: Optional session ID for multi-turn context

    Returns:
        Text result from the agent, or an error message string if the
        call fails (never raises — callers get degraded output, not crashes).
    """
    task = A2ATask(
        id=str(uuid.uuid4()),
        message=TaskMessage(parts=[MessagePart(text=query)]),
        sessionId=session_id,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{endpoint}/a2a",
                json=task.model_dump(),
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            result = A2AResult.model_validate(response.json())

            if result.status == "failed":
                return f"Agent at {endpoint} returned error: {result.error}"

            if result.artifacts and result.artifacts[0].parts:
                return result.artifacts[0].parts[0].text

            return "Agent returned no output."

    except httpx.TimeoutException:
        return f"Agent at {endpoint} timed out after {timeout}s."
    except httpx.ConnectError:
        return f"Agent at {endpoint} is unreachable. Check that the service is running."
    except Exception as e:
        return f"A2A call to {endpoint} failed: {e}"


def call_agent_sync(endpoint: str, query: str, timeout: int = 120) -> str:
    """
    Synchronous wrapper around call_agent for use inside Strands @tool functions.

    Strands tools are synchronous, so we need asyncio.run() to call the
    async HTTP client from within a @tool decorated function.
    """
    return asyncio.run(call_agent(endpoint, query, timeout))
