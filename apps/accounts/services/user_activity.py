"""Paginated user activity feed (CRUD + login sessions)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import UserAuditEntry
from apps.audit.utils.activity_actor import actor_options_from_ids, parse_actor_param
from apps.audit.utils.friendly_changes import enrich_user_audit_changes

CRUD_ACTIONS = ("created", "updated", "deleted")
LOGIN_ACTIONS = ("login",)


def _actor_display(entry: UserAuditEntry) -> str | None:
    if entry.actor_id is None:
        return None
    return entry.actor.get_username()


def _parse_bound(value: str | None, *, end_of_day: bool = False):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is not None:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt)
        return dt
    d = parse_date(value)
    if d is None:
        return None
    if end_of_day:
        dt = datetime.combine(d, datetime.max.time().replace(microsecond=0))
    else:
        dt = datetime.combine(d, datetime.min.time())
    return timezone.make_aware(dt)


def _parse_active(raw: str | None) -> bool | None:
    if raw is None or raw == "":
        return None
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "active"):
        return True
    if value in ("0", "false", "no", "inactive"):
        return False
    return None


def _item(entry: UserAuditEntry) -> dict[str, Any]:
    kind = "login" if entry.action == "login" else "crud"
    return {
        "kind": kind,
        "audit_id": entry.id,
        "action": entry.action,
        "occurred_at": entry.created_at,
        "actor_display": _actor_display(entry),
        "summary": entry.summary,
        "subject_id": entry.subject_id,
        "subject_username": entry.subject_username,
        "subject_display": entry.subject_display or entry.subject_username,
        "subject_role": entry.subject_role or None,
        "subject_is_active": entry.subject_is_active,
        "changes": enrich_user_audit_changes(
            entry.changes if isinstance(entry.changes, dict) else {}
        )
        or {},
    }


def _base_qs(*, kind: str, user_id: int | None = None):
    qs = UserAuditEntry.objects.select_related("actor", "subject")
    if user_id is not None:
        qs = qs.filter(subject_id=user_id)
    if kind == "crud":
        qs = qs.filter(action__in=CRUD_ACTIONS)
    elif kind == "login":
        qs = qs.filter(action__in=LOGIN_ACTIONS)
    return qs


def list_user_activity_actors() -> dict[str, Any]:
    qs = _base_qs(kind="all")
    user_ids = qs.exclude(actor_id=None).values_list("actor_id", flat=True).distinct()
    has_system = qs.filter(actor_id__isnull=True).exists()
    return {
        "results": actor_options_from_ids(user_ids),
        "has_system": has_system,
    }


def build_user_activity(
    *,
    kind: str = "all",
    role: str | None = None,
    is_active: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    actor: str | None = None,
    user_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    kind = (kind or "all").lower()
    if kind not in ("all", "crud", "login"):
        kind = "all"

    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    qs = _base_qs(kind=kind, user_id=user_id)

    if role:
        qs = qs.filter(subject_role=role)

    active = _parse_active(is_active)
    if active is not None:
        qs = qs.filter(subject_is_active=active)

    bound_from = _parse_bound(date_from, end_of_day=False)
    bound_to = _parse_bound(date_to, end_of_day=True)
    if bound_from is not None:
        qs = qs.filter(created_at__gte=bound_from)
    if bound_to is not None:
        qs = qs.filter(created_at__lte=bound_to)

    actor_system, actor_user_id = parse_actor_param(actor)
    if actor_system:
        qs = qs.filter(actor_id__isnull=True)
    elif actor_user_id is not None:
        qs = qs.filter(actor_id=actor_user_id)

    qs = qs.order_by("-created_at")
    count = qs.count()
    start = (page - 1) * page_size
    rows = list(qs[start : start + page_size])

    return {
        "count": count,
        "page": page,
        "page_size": page_size,
        "results": [_item(row) for row in rows],
    }
