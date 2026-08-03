"""Paginated shipping line catalog activity feed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import ShippingLineAuditEntry

CRUD_ACTIONS = ("created", "updated", "deleted")


def _actor_display(entry: ShippingLineAuditEntry) -> str | None:
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


def _item(entry: ShippingLineAuditEntry) -> dict[str, Any]:
    changes = entry.changes or {}
    entity = changes.get("entity") if isinstance(changes, dict) else None
    return {
        "kind": "crud",
        "action": entry.action,
        "occurred_at": entry.created_at,
        "actor_display": _actor_display(entry),
        "summary": entry.summary,
        "shipping_line_id": entry.shipping_line_id,
        "shipping_line_code": entry.shipping_line_code,
        "shipping_line_name": entry.shipping_line_name,
        "group_name": entry.group_name or None,
        "changes": changes,
        "entity": entity if isinstance(entity, dict) else None,
    }


def build_shipping_line_activity(
    *,
    kind: str = "all",
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    kind = (kind or "all").lower()
    if kind not in ("all", "crud"):
        kind = "all"

    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    qs = ShippingLineAuditEntry.objects.select_related("actor", "shipping_line")
    if kind == "crud":
        qs = qs.filter(action__in=CRUD_ACTIONS)

    bound_from = _parse_bound(date_from, end_of_day=False)
    bound_to = _parse_bound(date_to, end_of_day=True)
    if bound_from is not None:
        qs = qs.filter(created_at__gte=bound_from)
    if bound_to is not None:
        qs = qs.filter(created_at__lte=bound_to)

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
