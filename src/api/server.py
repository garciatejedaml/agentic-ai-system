"""
FastAPI server – OpenAI-compatible chat completions endpoint.

Wraps the agentic pipeline so any OpenAI-compatible client
(Continue.dev, curl, etc.) can talk to the local agent.

Session management:
  Conversations are persisted in DynamoDB (agent-sessions table).
  Each request can include a `session_id` to continue a prior conversation.
  If omitted, a new session is created and returned in the response.
  This enables multi-turn conversations across the distributed agent services.

Usage:
    uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload

Endpoint:
    POST http://localhost:8000/v1/chat/completions
"""
import json
import logging
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.config import config
from src.observability import setup_observability

logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic AI System", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for running synchronous agent code from async context
# 8 workers for ~500 users: agents are I/O-bound (LLM calls), so threads
# can serve more concurrent requests than CPU cores would suggest
_executor = ThreadPoolExecutor(max_workers=8)


# Initialize once at startup
@app.on_event("startup")
def on_startup():
    config.validate()
    setup_observability()
    # Pre-load the graph so first request is faster
    from src.graph.workflow import get_graph  # noqa: F401


# ── Request / Response schemas (OpenAI-compatible + session extension) ─────────

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "agentic-ai-system"
    messages: List[Message]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    # ── Session extension fields ─────────────────────────────────────────────
    # These extend the OpenAI schema; standard clients simply ignore them.

    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Conversation session ID. Pass the value returned from the previous "
            "response to continue a multi-turn conversation. Omit to start a new session."
        ),
    )
    user: Optional[str] = Field(
        default=None,
        description="Trader / user identifier (e.g. T_HY_001). Used for session scoping and audit.",
    )
    desk_name: Optional[str] = Field(
        default=None,
        description="Trading desk override (HY | IG | EM | RATES). Auto-derived from `user` if omitted.",
    )


# ── Agent runner ───────────────────────────────────────────────────────────────

def _run_agent(query: str) -> str:
    """Synchronous call to the agentic pipeline."""
    from src.graph.workflow import run_query
    state = run_query(query)
    return state.get("final_response") or "No response generated."


# ── Response builders ──────────────────────────────────────────────────────────

def _build_response(content: str, model: str, session_id: str) -> dict:
    """
    Build an OpenAI-compatible response with session_id extension.

    The `session_id` field is non-standard but follows the pattern used by
    several enterprise OpenAI-compatible APIs. Clients that don't understand
    it simply ignore it; clients that do can pass it back to continue the session.
    """
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "session_id": session_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def _stream_response(content: str, model: str, session_id: str):
    """Yield the response word-by-word as SSE chunks."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    # First chunk: include session_id so streaming clients can capture it
    meta_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "session_id": session_id,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(meta_chunk)}\n\n"

    words = content.split(" ")
    for i, word in enumerate(words):
        text = word if i == 0 else " " + word
        chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.01)

    done_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done_chunk)}\n\n"
    yield "data: [DONE]\n\n"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "Agentic AI System", "version": "2.0.0"}


@app.get("/v1/models")
def list_models():
    """Required by some OpenAI clients to discover available models."""
    return {
        "object": "list",
        "data": [
            {
                "id": "agentic-ai-system",
                "object": "model",
                "created": 0,
                "owned_by": "local",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    from src.api.sessions import (
        build_context_string,
        create_session,
        load_session,
        save_session,
    )

    # ── 1. Extract the current user message ──────────────────────────────────
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )
    if not user_message:
        session_id = request.session_id or create_session(
            user_id=request.user or "",
            desk_name=request.desk_name or "",
        )
        return _build_response("No user message found.", request.model, session_id)

    # ── 2. Session: load or create ───────────────────────────────────────────
    user_id = request.user or ""
    desk_name = request.desk_name or ""

    if request.session_id:
        session_id = request.session_id
        history = load_session(session_id)
        logger.info("[session:%s] Loaded %d messages for user %s", session_id, len(history), user_id)
    else:
        session_id = create_session(user_id=user_id, desk_name=desk_name)
        history = []
        logger.info("[session:%s] New session for user %s", session_id, user_id)

    # ── 3. Build enriched query with conversation context ────────────────────
    context_str = build_context_string(history)
    if context_str:
        enriched_query = f"{context_str}\n\n[Current Query]\n{user_message}"
    else:
        enriched_query = user_message

    # ── 4. Run agent pipeline (synchronous, offloaded to thread pool) ────────
    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(_executor, _run_agent, enriched_query)

    # ── 5. Persist session (fire-and-forget via executor to not block response) ──
    loop.run_in_executor(
        _executor,
        save_session,
        session_id,
        user_message,   # store the original message, not the enriched one
        content,
        user_id,
        desk_name,
    )

    # ── 6. Return response with session_id ───────────────────────────────────
    if request.stream:
        return StreamingResponse(
            _stream_response(content, request.model, session_id),
            media_type="text/event-stream",
        )

    return _build_response(content, request.model, session_id)
