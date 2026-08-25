"""Shared helpers for activity feed actor filters."""

from __future__ import annotations

from typing import Any, Iterable

from django.contrib.auth import get_user_model


def parse_actor_param(raw: str | None) -> tuple[bool, int | None]:
    """
    Returns (system_only, user_id).

    - None / empty → no actor filter
    - "system" / "sistema" → only rows with no human actor
    - numeric id → that user
    """
    if raw is None:
        return False, None
    value = str(raw).strip().lower()
    if not value:
        return False, None
    if value in ("system", "sistema"):
        return True, None
    try:
        user_id = int(value)
    except (TypeError, ValueError):
        return False, None
    if user_id <= 0:
        return False, None
    return False, user_id


def actor_options_from_ids(user_ids: Iterable[int]) -> list[dict[str, Any]]:
    """Serialize users that appear in an activity feed (ordered by username)."""
    ids = sorted({int(uid) for uid in user_ids if uid})
    if not ids:
        return []
    User = get_user_model()
    users = User.objects.filter(id__in=ids).order_by("username")
    return [{"id": u.id, "label": u.get_username()} for u in users]
