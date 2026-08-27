"""Paginated LTA agreement activity feed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import LtaAuditEntry
from apps.audit.utils.activity_actor import actor_options_from_ids, parse_actor_param
from apps.audit.utils.friendly_changes import enrich_lta_audit_changes
from apps.bookings.services.validation.legend_labels import port_legend_label
from apps.catalogs.models import Port, ShippingLine

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


def _item_kind(entry: LtaAuditEntry) -> str:
    """CRUD vs vinculación; async job completions use link_bookings or job_kind."""
    if entry.action in LINK_ACTIONS:
        return "link"
    changes = entry.changes if isinstance(entry.changes, dict) else {}
    job_kind = changes.get("job_kind")
    if job_kind in ("link", "resync", "destroy") and changes.get("job_status") in (
        "success",
        "failed",
        "queued",
    ):
        # Queued create/update/delete stay CRUD; completion of link/resync is link.
        if entry.action in CRUD_ACTIONS and changes.get("job_status") == "queued":
            return "crud"
        if job_kind in ("link", "resync"):
            return "link"
    return "crud"


def _entity_blob(changes: dict[str, Any]) -> dict[str, Any]:
    for key in ("entity", "created", "deleted"):
        blob = changes.get(key)
        if isinstance(blob, dict):
            return blob
    return {}


def _str_field(blob: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = blob.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _build_port_line_maps(
    rows: list[LtaAuditEntry],
) -> tuple[dict[int, str], dict[str, str]]:
    port_ids = {e.port_id for e in rows if e.port_id}
    line_codes = {
        (e.shipping_line_code or "").strip()
        for e in rows
        if (e.shipping_line_code or "").strip()
    }
    ports_by_id: dict[int, str] = {}
    if port_ids:
        for port in Port.objects.filter(pk__in=port_ids):
            ports_by_id[port.pk] = port_legend_label(port) or port.name or port.code
    lines_by_code: dict[str, str] = {}
    if line_codes:
        for line in ShippingLine.objects.filter(code__in=line_codes):
            lines_by_code[line.code] = (line.name or line.code or "").strip()
    return ports_by_id, lines_by_code


def _item(
    entry: LtaAuditEntry,
    *,
    ports_by_id: dict[int, str],
    lines_by_code: dict[str, str],
) -> dict[str, Any]:
    kind = _item_kind(entry)
    changes = enrich_lta_audit_changes(
        entry.changes if isinstance(entry.changes, dict) else {}
    ) or {}
    blob = _entity_blob(changes)
    port_name = (
        _str_field(blob, "port_name")
        or (ports_by_id.get(entry.port_id) if entry.port_id else "")
        or ""
    )
    shipping_line_name = (
        _str_field(blob, "shipping_line_name")
        or lines_by_code.get((entry.shipping_line_code or "").strip(), "")
        or ""
    )
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
        "port_name": port_name or None,
        "shipping_line_code": entry.shipping_line_code or None,
        "shipping_line_name": shipping_line_name or None,
        "changes": changes,
        "entity": entity if isinstance(entity, dict) else None,
    }


def _base_qs(*, allowed_ports: list[int] | None, kind: str):
    qs = LtaAuditEntry.objects.select_related("actor", "agreement")
    if kind == "crud":
        qs = qs.filter(action__in=CRUD_ACTIONS)
    elif kind == "link":
        # Include async link/resync completions (action=link_bookings).
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
    ports_by_id, lines_by_code = _build_port_line_maps(rows)

    return {
        "count": count,
        "page": page,
        "page_size": page_size,
        "results": [
            _item(row, ports_by_id=ports_by_id, lines_by_code=lines_by_code)
            for row in rows
        ],
    }
