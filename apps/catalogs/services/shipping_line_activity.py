"""Paginated shipping line catalog activity feed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import ShippingLineAuditEntry
from apps.audit.utils.activity_actor import actor_options_from_ids, parse_actor_param
from apps.audit.utils.catalog_activity_filter import (
    catalog_actions_for_operation,
    norm_activity_operation,
)
from apps.audit.utils.friendly_changes import enrich_shipping_line_audit_changes

CRUD_ACTIONS = (
    "created",
    "updated",
    "deleted",
    "vessel_created",
    "vessel_updated",
    "vessel_deleted",
)

# Legacy kind param (deprecated).
ACTIVITY_KINDS = ("all", "crud")
ACTIVITY_OPERATIONS = ("all", "create", "update", "delete")


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
    changes = (
        enrich_shipping_line_audit_changes(
            entry.changes if isinstance(entry.changes, dict) else {}
        )
        or {}
    )
    entity = changes.get("entity") if isinstance(changes, dict) else None
    return {
        "kind": "crud",
        "audit_id": entry.id,
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


def _resolve_action_filter(
    *,
    operation: str = "all",
    kind: str | None = None,
) -> tuple[str, ...] | None:
    operation = norm_activity_operation(operation, ACTIVITY_OPERATIONS, "all")
    legacy = (kind or "all").lower()
    if legacy == "crud":
        return CRUD_ACTIONS
    if operation == "all":
        return None
    return catalog_actions_for_operation(operation, CRUD_ACTIONS)


def _base_qs(
    *,
    action_filter: tuple[str, ...] | None = None,
    shipping_line_id: int | None = None,
):
    qs = ShippingLineAuditEntry.objects.select_related("actor", "shipping_line")
    if shipping_line_id is not None:
        qs = qs.filter(shipping_line_id=shipping_line_id)
    if action_filter is not None:
        qs = qs.filter(action__in=action_filter)
    return qs


def list_shipping_line_activity_actors() -> dict[str, Any]:
    qs = _base_qs()
    user_ids = qs.exclude(actor_id=None).values_list("actor_id", flat=True).distinct()
    has_system = qs.filter(actor_id__isnull=True).exists()
    return {
        "results": actor_options_from_ids(user_ids),
        "has_system": has_system,
    }


def build_shipping_line_activity(
    *,
    operation: str = "all",
    kind: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    actor: str | None = None,
    shipping_line_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    action_filter = _resolve_action_filter(operation=operation, kind=kind)
    qs = _base_qs(action_filter=action_filter, shipping_line_id=shipping_line_id)

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
