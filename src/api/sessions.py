"""
Session Store — DynamoDB-backed conversation memory

Provides stateful multi-turn conversations across isolated agent containers.
Each session stores the last MAX_MESSAGES exchanges with a configurable TTL.

Designed for ~500 concurrent users on DynamoDB PAY_PER_REQUEST billing:
  - No capacity planning required
  - Scales automatically; DynamoDB handles thousands of RPS
  - TTL-based expiry (no manual cleanup needed)
  - Graceful degradation: if DynamoDB is unavailable, conversations continue
    without history (stateless fallback) rather than failing hard

Table: {name_prefix}-sessions
  PK:  session_id  (String) — UUID, one per conversation
  GSI: ByUser     (user_id) — list all sessions for a trader

Item schema:
  {
    "session_id":  "sess-uuid",
    "user_id":     "T_HY_001",       ← trader ID (optional)
    "desk_name":   "HY",             ← derived from user_id or explicit
    "user_role":   "business",       ← "business" | "technical"
    "messages": [                    ← last MAX_MESSAGES only
      {"role": "user",      "content": "Top HY traders?"},
      {"role": "assistant", "content": "Sarah Mitchell leads..."},
    ],
    "message_count": 12,             ← total turns (including rotated-out ones)
    "created_at":    "2026-02-23T14:00:00Z",
    "updated_at":    "2026-02-23T14:05:00Z",
    "ttl":           1740456000,     ← Unix epoch for DynamoDB auto-expiry
  }

Environment:
  AWS_ENDPOINT_URL      → http://localstack:4566 (local dev) or empty (AWS)
  SESSION_TABLE         → override table name (default: agentic-ai-staging-sessions)
  SESSION_TTL_HOURS     → session lifetime in hours (default: 24)
  SESSION_MAX_MESSAGES  → max messages to retain per session (default: 20)
  SESSION_MAX_MSG_CHARS → max chars per message content (default: 1000)
"""
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

_TABLE_NAME = os.getenv("SESSION_TABLE", "agentic-ai-staging-sessions")
_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "") or None  # None = real AWS

# Conversation window: 20 messages = 10 turns (user + assistant per turn)
MAX_MESSAGES: int = int(os.getenv("SESSION_MAX_MESSAGES", "20"))
# Per-message truncation prevents context window overflow in the LLM
MAX_MSG_CHARS: int = int(os.getenv("SESSION_MAX_MSG_CHARS", "1000"))
TTL_HOURS: int = int(os.getenv("SESSION_TTL_HOURS", "24"))

# Desk name mapping from trader ID prefix
_DESK_MAP = {
    "T_HY":    "HY",
    "T_IG":    "IG",
    "T_EM":    "EM",
    "T_RATES": "RATES",
}


# ── DynamoDB client ────────────────────────────────────────────────────────────

def _table():
    kwargs = {"region_name": _REGION}
    if _ENDPOINT:
        kwargs["endpoint_url"] = _ENDPOINT
    return boto3.resource("dynamodb", **kwargs).Table(_TABLE_NAME)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _derive_desk(user_id: str) -> str:
    """Infer trading desk from trader ID (e.g. T_HY_001 → HY)."""
    for prefix, desk in _DESK_MAP.items():
        if user_id.upper().startswith(prefix):
            return desk
    return "GENERAL"


def _derive_role(user_id: str) -> str:
    """Classify user as 'business' (trader) or 'technical' (system/dev)."""
    if user_id.upper().startswith("T_"):
        return "business"
    return "technical"


def _ttl() -> int:
    return int(time.time()) + TTL_HOURS * 3600


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _truncate(text: str, max_chars: int = MAX_MSG_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


# ── Public API ────────────────────────────────────────────────────────────────

def create_session(user_id: str = "", desk_name: str = "") -> str:
    """
    Create a new session and return the session_id.

    Called when the client doesn't provide a session_id (first message).
    """
    session_id = f"sess-{uuid.uuid4().hex[:16]}"
    desk = desk_name or _derive_desk(user_id)
    now = _now_iso()

    try:
        _table().put_item(Item={
            "session_id":    session_id,
            "user_id":       user_id or "anonymous",
            "desk_name":     desk,
            "user_role":     _derive_role(user_id),
            "messages":      [],
            "message_count": 0,
            "created_at":    now,
            "updated_at":    now,
            "ttl":           _ttl(),
        })
    except ClientError as e:
        logger.warning("[sessions] Could not create session in DynamoDB: %s", e)
        # Still return a session_id — it just won't be persisted

    return session_id


def load_session(session_id: str) -> list[dict]:
    """
    Load conversation history for a session.

    Returns a list of {role, content} dicts, or [] if not found / DynamoDB down.
    """
    try:
        resp = _table().get_item(
            Key={"session_id": session_id},
            ProjectionExpression="messages",
        )
        item = resp.get("Item")
        if not item:
            return []
        return item.get("messages", [])
    except ClientError as e:
        logger.warning("[sessions] Could not load session %s: %s", session_id, e)
        return []


def save_session(
    session_id: str,
    new_user_message: str,
    assistant_response: str,
    user_id: str = "",
    desk_name: str = "",
) -> None:
    """
    Append a new turn to the session and persist.

    Rotates out oldest messages when MAX_MESSAGES is exceeded.
    Truncates each message content to MAX_MSG_CHARS to keep items lean.
    Silently fails if DynamoDB is unavailable.
    """
    try:
        # Load current history
        current = load_session(session_id)

        # Append new turn
        current.append({"role": "user",      "content": _truncate(new_user_message)})
        current.append({"role": "assistant", "content": _truncate(assistant_response)})

        # Rotate: keep only the last MAX_MESSAGES
        if len(current) > MAX_MESSAGES:
            current = current[-MAX_MESSAGES:]

        desk = desk_name or _derive_desk(user_id)
        now = _now_iso()

        _table().update_item(
            Key={"session_id": session_id},
            UpdateExpression=(
                "SET messages = :msgs, updated_at = :now, #ttl = :ttl, "
                "message_count = message_count + :inc, "
                "user_id = if_not_exists(user_id, :uid), "
                "desk_name = if_not_exists(desk_name, :desk)"
            ),
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":msgs": current,
                ":now":  now,
                ":ttl":  _ttl(),
                ":inc":  1,
                ":uid":  user_id or "anonymous",
                ":desk": desk,
            },
        )
    except ClientError as e:
        logger.warning("[sessions] Could not save session %s: %s", session_id, e)


def build_context_string(messages: list[dict]) -> str:
    """
    Format conversation history for injection into the agent query.

    The output is prepended to the current user query so the LLM has
    context from previous turns:

      [Conversation History]
      Trader: Who are the top HY traders?
      System: Sarah Mitchell leads with 72.26% hit rate...

      [Current Query]
      <the actual question>
    """
    if not messages:
        return ""

    lines = ["[Conversation History — previous turns in this session]"]
    for msg in messages:
        label = "Trader" if msg["role"] == "user" else "System"
        lines.append(f"{label}: {msg['content']}")

    return "\n".join(lines)
