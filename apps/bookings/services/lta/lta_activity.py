"""Paginated LTA agreement activity feed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import LtaAuditEntry
from apps.audit.utils.activity_actor import actor_options_from_ids, parse_actor_param

CRUD_ACTIONS = ("created", "updated", "deleted")
LINK_ACTIONS = ("link_bookings",)


def _actor_display(entry: LtaAuditEntry) -> str | None:
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


def _item(entry: LtaAuditEntry) -> dict[str, Any]:
    kind = "link" if entry.action == "link_bookings" else "crud"
    changes = entry.changes or {}
    entity = changes.get("entity") if isinstance(changes, dict) else None
    return {
        "kind": kind,
        "action": entry.action,
        "occurred_at": entry.created_at,
        "actor_display": _actor_display(entry),
        "summary": entry.summary,
        "agreement_id": entry.agreement_id,
        "agreement_code": entry.agreement_code,
        "agreement_name": entry.agreement_name,
        "port_code": entry.port_code or None,
        "shipping_line_code": entry.shipping_line_code or None,
        "changes": changes,
        "entity": entity if isinstance(entity, dict) else None,
    }


def _base_qs(*, allowed_ports: list[int] | None, kind: str):
    qs = LtaAuditEntry.objects.select_related("actor", "agreement")
    if kind == "crud":
        qs = qs.filter(action__in=CRUD_ACTIONS)
    elif kind == "link":
        qs = qs.filter(action__in=LINK_ACTIONS)
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    return qs


def list_lta_activity_actors(
    *,
    allowed_ports: list[int] | None,
) -> dict[str, Any]:
    qs = _base_qs(allowed_ports=allowed_ports, kind="all")
    user_ids = qs.exclude(actor_id=None).values_list("actor_id", flat=True).distinct()
    has_system = qs.filter(actor_id__isnull=True).exists()
    return {
        "results": actor_options_from_ids(user_ids),
        "has_system": has_system,
    }


def build_lta_activity(
    *,
    allowed_ports: list[int] | None,
    kind: str = "all",
    date_from: str | None = None,
    date_to: str | None = None,
    actor: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    kind = (kind or "all").lower()
    if kind not in ("all", "crud", "link"):
        kind = "all"

    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    qs = _base_qs(allowed_ports=allowed_ports, kind=kind)

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
