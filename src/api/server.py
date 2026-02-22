"""
FastAPI server – OpenAI-compatible chat completions endpoint.

Wraps the agentic pipeline so any OpenAI-compatible client
(Continue.dev, curl, etc.) can talk to the local agent.

Usage:
    uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload

Endpoint:
    POST http://localhost:8000/v1/chat/completions
"""
import time
import uuid
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.config import config
from src.observability import setup_observability

logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic AI System", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for running synchronous agent code from async context
_executor = ThreadPoolExecutor(max_workers=4)

# Initialize once at startup
@app.on_event("startup")
def on_startup():
    config.validate()
    setup_observability()
    # Pre-load the graph so first request is faster
    from src.graph.workflow import get_graph  # noqa: F401


# ── Request / Response schemas (OpenAI-compatible) ────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "agentic-ai-system"
    messages: List[Message]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


# ── Helper ─────────────────────────────────────────────────────────────────────

def _run_agent(user_message: str) -> str:
    """Synchronous call to the agentic pipeline."""
    from src.graph.workflow import run_query
    state = run_query(user_message)
    return state.get("final_response") or "No response generated."


def _build_response(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def _stream_response(content: str, model: str):
    """Yield the response word-by-word as SSE chunks (fake streaming)."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

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
        import json
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.01)

    # Final chunk
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
    return {"status": "ok", "service": "Agentic AI System"}


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
    # Extract the last user message
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )

    if not user_message:
        return _build_response("No user message found.", request.model)

    # Run agent in thread pool (it's synchronous)
    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(_executor, _run_agent, user_message)

    if request.stream:
        return StreamingResponse(
            _stream_response(content, request.model),
            media_type="text/event-stream",
        )

    return _build_response(content, request.model)
