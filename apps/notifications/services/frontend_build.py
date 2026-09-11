"""Frontend build id publish + WebSocket broadcast (authenticated clients)."""

from __future__ import annotations

import logging

import redis
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

logger = logging.getLogger(__name__)

REDIS_KEY = "portpax:frontend_build_id"
APP_UPDATES_GROUP = "app_updates"


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)


def get_frontend_build_id() -> str | None:
    try:
        value = _redis().get(REDIS_KEY)
    except redis.RedisError:
        logger.exception("Failed to read frontend build id from Redis")
        return None
    if not value:
        return None
    return str(value)


def publish_frontend_build_id(build_id: str) -> dict:
    """
    Persist build_id and broadcast to connected clients when it changes.

    Returns {"build_id", "changed", "broadcast"}.
    """
    cleaned = (build_id or "").strip()
    if not cleaned:
        raise ValueError("build_id is required")

    previous = get_frontend_build_id()
    changed = previous != cleaned
    if changed:
        try:
            _redis().set(REDIS_KEY, cleaned)
        except redis.RedisError:
            logger.exception("Failed to store frontend build id in Redis")
            raise

    broadcast = False
    if changed:
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                APP_UPDATES_GROUP,
                {
                    "type": "app_update.message",
                    "payload": {"build_id": cleaned},
                },
            )
            broadcast = True

    return {"build_id": cleaned, "changed": changed, "broadcast": broadcast}
