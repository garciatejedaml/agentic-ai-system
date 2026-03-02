"""
Daily request rate limiter — DynamoDB-backed per-user counter.

Table schema: {TOKEN_USAGE_TABLE}
  PK: user_id  (String)
  SK: date     (String, YYYY-MM-DD)
  Attributes:
    request_count (Number) — incremented atomically on each API call
    ttl           (Number) — Unix epoch 2 days out; DynamoDB auto-expires the item

Behavior:
  - check_and_increment() atomically increments request_count.
  - Raises RateLimitExceeded when request_count would exceed DAILY_REQUEST_LIMIT.
  - Graceful degradation: if DynamoDB is unavailable the request is allowed
    (logged as a warning). Never hard-fails the API.
  - Disabled when RATE_LIMIT_ENABLED=false (e.g. local dev without LocalStack).
"""
import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from src.config import config

logger = logging.getLogger(__name__)

_dynamodb = None


def _get_table():
    global _dynamodb
    if _dynamodb is None:
        kwargs = {"region_name": config.AWS_REGION}
        if config.DYNAMODB_ENDPOINT:
            kwargs["endpoint_url"] = config.DYNAMODB_ENDPOINT
        _dynamodb = boto3.resource("dynamodb", **kwargs)
    return _dynamodb.Table(config.TOKEN_USAGE_TABLE)


class RateLimitExceeded(Exception):
    """Raised when the user has exhausted their daily request quota."""


def check_and_increment(user_id: str) -> None:
    """
    Atomically increment the daily request counter for user_id.

    Raises:
        RateLimitExceeded: if the user has reached DAILY_REQUEST_LIMIT today.
    """
    if not config.RATE_LIMIT_ENABLED:
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # TTL: auto-expire item after 2 days (DynamoDB cleanup)
    ttl = int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp())
    limit = config.DAILY_REQUEST_LIMIT

    try:
        table = _get_table()
        table.update_item(
            Key={"user_id": user_id, "date": today},
            UpdateExpression="ADD request_count :one SET #ttl = if_not_exists(#ttl, :ttl)",
            ConditionExpression="attribute_not_exists(request_count) OR request_count < :limit",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":one": 1,
                ":limit": limit,
                ":ttl": ttl,
            },
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ConditionalCheckFailedException":
            raise RateLimitExceeded(
                f"Daily request limit of {limit} reached for user '{user_id}'. "
                "Resets at midnight UTC."
            )
        # DynamoDB unavailable or table missing → allow request, log warning
        logger.warning(
            "[rate_limiter] DynamoDB unavailable (%s: %s) — request allowed without counting.",
            code,
            e.response["Error"]["Message"],
        )
    except Exception as exc:
        # Any other error (network, credentials) → allow request, log warning
        logger.warning("[rate_limiter] Unexpected error — request allowed: %s", exc)


def get_usage(user_id: str) -> dict:
    """
    Return today's usage stats for a user.
    Returns {"request_count": 0, "limit": N} if no record exists or on error.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        table = _get_table()
        response = table.get_item(Key={"user_id": user_id, "date": today})
        item = response.get("Item", {})
        return {
            "request_count": int(item.get("request_count", 0)),
            "limit": config.DAILY_REQUEST_LIMIT,
            "date": today,
        }
    except Exception:
        return {"request_count": 0, "limit": config.DAILY_REQUEST_LIMIT, "date": today}
