"""Online presence for authenticated WebSocket clients (multi-tab safe)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis
from django.conf import settings

from apps.accounts.models import UserProfile
from apps.accounts.services.user_audit import role_label, user_display_name

logger = logging.getLogger(__name__)

PRESENCE_GROUP = "presence"
REDIS_USERS_KEY = "portpax:presence:users"
REDIS_CHANNELS_PREFIX = "portpax:presence:channels:"
REDIS_STATUS_PREFIX = "portpax:presence:status:"

STATUS_ACTIVE = "active"
STATUS_IDLE = "idle"
VALID_STATUSES = frozenset({STATUS_ACTIVE, STATUS_IDLE})


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)


def _channels_key(user_id: int) -> str:
    return f"{REDIS_CHANNELS_PREFIX}{user_id}"


def _status_key(user_id: int) -> str:
    return f"{REDIS_STATUS_PREFIX}{user_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _aggregate_status(r: redis.Redis, user_id: int) -> str:
    values = r.hvals(_status_key(user_id))
    if any(value == STATUS_ACTIVE for value in values):
        return STATUS_ACTIVE
    if values:
        return STATUS_IDLE
    return STATUS_ACTIVE


def presence_user_payload(
    user,
    *,
    status: str = STATUS_ACTIVE,
    last_seen: str | None = None,
) -> dict[str, Any]:
    role = ""
    avatar: str | None = None
    try:
        profile = user.profile
        role = profile.role or ""
        if profile.avatar:
            avatar = profile.avatar.url
    except UserProfile.DoesNotExist:
        pass
    cleaned = status if status in VALID_STATUSES else STATUS_ACTIVE
    return {
        "id": user.pk,
        "display_name": user_display_name(user),
        "username": user.get_username(),
        "role": role,
        "role_label": role_label(role),
        "avatar": avatar,
        "status": cleaned,
        "last_seen": last_seen or _now_iso(),
    }


def list_online_users() -> list[dict[str, Any]]:
    try:
        raw = _redis().hgetall(REDIS_USERS_KEY)
    except redis.RedisError:
        logger.exception("Failed to read presence users from Redis")
        return []
    users: list[dict[str, Any]] = []
    for value in raw.values():
        try:
            row = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            continue
        if "status" not in row:
            row["status"] = STATUS_ACTIVE
        users.append(row)
    users.sort(
        key=lambda row: (
            0 if row.get("status") == STATUS_ACTIVE else 1,
            (row.get("display_name") or "").lower(),
        )
    )
    return users


def _store_user_payload(r: redis.Redis, user_id: int, payload: dict[str, Any]) -> None:
    r.hset(REDIS_USERS_KEY, str(user_id), json.dumps(payload))


def register_presence(user, channel_name: str) -> tuple[bool, list[dict[str, Any]]]:
    """
    Track a WebSocket connection for ``user``.

    Returns (is_first_connection, online_users_snapshot).
    """
    user_id = int(user.pk)
    r = _redis()
    try:
        added = r.sadd(_channels_key(user_id), channel_name)
        r.hset(_status_key(user_id), channel_name, STATUS_ACTIVE)
        status = _aggregate_status(r, user_id)
        payload = presence_user_payload(user, status=status, last_seen=_now_iso())
        _store_user_payload(r, user_id, payload)
    except redis.RedisError:
        logger.exception("Failed to register presence for user %s", user_id)
        return False, list_online_users()
    return bool(added), list_online_users()


def unregister_presence(user_id: int, channel_name: str) -> tuple[bool, list[dict[str, Any]]]:
    """
    Drop a WebSocket connection.

    Returns (went_fully_offline, online_users_snapshot).
    """
    r = _redis()
    key = _channels_key(user_id)
    try:
        r.srem(key, channel_name)
        r.hdel(_status_key(user_id), channel_name)
        remaining = r.scard(key)
        if remaining == 0:
            r.delete(key)
            r.delete(_status_key(user_id))
            r.hdel(REDIS_USERS_KEY, str(user_id))
            return True, list_online_users()
        # Still online on another tab — refresh aggregate status.
        raw = r.hget(REDIS_USERS_KEY, str(user_id))
        if raw:
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                payload = {"id": user_id}
            payload["status"] = _aggregate_status(r, user_id)
            payload["last_seen"] = _now_iso()
            _store_user_payload(r, user_id, payload)
    except redis.RedisError:
        logger.exception("Failed to unregister presence for user %s", user_id)
        return False, list_online_users()
    return False, list_online_users()


def update_presence_status(
    user_id: int,
    channel_name: str,
    status: str,
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Update activity status for one connection.

    Returns (changed, online_users_snapshot).
    """
    cleaned = (status or "").strip().lower()
    if cleaned not in VALID_STATUSES:
        return False, list_online_users()

    r = _redis()
    try:
        if not r.sismember(_channels_key(user_id), channel_name):
            return False, list_online_users()
        r.hset(_status_key(user_id), channel_name, cleaned)
        aggregated = _aggregate_status(r, user_id)
        raw = r.hget(REDIS_USERS_KEY, str(user_id))
        if not raw:
            return False, list_online_users()
        payload = json.loads(raw)
        previous = payload.get("status")
        payload["status"] = aggregated
        payload["last_seen"] = _now_iso()
        changed = previous != aggregated
        _store_user_payload(r, user_id, payload)
    except (redis.RedisError, TypeError, json.JSONDecodeError):
        logger.exception("Failed to update presence status for user %s", user_id)
        return False, list_online_users()
    return changed, list_online_users()
