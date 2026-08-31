"""Unified booking activity feed (single audits + mass import batches)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import BookingAuditEntry
from apps.audit.utils.activity_actor import actor_options_from_ids, parse_actor_param
from apps.bookings.models import Booking, BookingImportBatch

SINGLE_ACTIONS = (
    "created",
    "operational_update",
    "identity_update",
    "status_change",
    "lta_linked",
    "lta_unlinked",
)

# Structural kinds + creation-origin filters (Tipo dropdown).
ACTIVITY_KINDS = (
    "all",
    "single",
    "bulk",
    "wizard",
    "mass_import",
    "berthing_import",
    "lta_generate",
)

MASS_IMPORT_SOURCES = ("mass_import", "import_file", "import_paste")


def _user_display(user) -> str | None:
    if user is None:
        return None
    return user.get_username()


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


def _single_item(entry: BookingAuditEntry) -> dict[str, Any]:
    code = entry.booking_code or None
    if not code and entry.booking_id and entry.booking is not None:
        code = entry.booking.booking_code
    changes = entry.changes or {}
    entity = changes.get("entity") if isinstance(changes, dict) else None
    return {
        "kind": "single",
        "audit_id": entry.id,
        "action": entry.action,
        "occurred_at": entry.created_at,
        "user_display": _user_display(entry.user),
        "summary": entry.summary,
        "booking_id": entry.booking_id,
        "booking_code": code,
        "batch_id": None,
        "created_count": None,
        "failed_count": None,
        "not_created_count": None,
        "changes": changes,
        "entity": entity if isinstance(entity, dict) else None,
    }


def _bulk_item(batch: BookingImportBatch) -> dict[str, Any]:
    return {
        "kind": "bulk",
        "action": "bulk_create",
        "occurred_at": batch.created_at,
        "user_display": _user_display(batch.created_by),
        "summary": (
            f"Importación: {batch.created_count} creadas, "
            f"{batch.failed_count} fallidas, "
            f"{max(0, len(batch.retry_rows or []) - batch.failed_count)} no creadas"
        ),
        "booking_id": None,
        "booking_code": None,
        "batch_id": batch.id,
        "created_count": batch.created_count,
        "failed_count": batch.failed_count,
        "not_created_count": max(
            0, len(batch.retry_rows or []) - batch.failed_count
        ),
        "label": batch.label,
    }


def _audit_queryset(
    *,
    allowed_ports: list[int] | None,
    date_from,
    date_to,
    actor_system: bool = False,
    actor_user_id: int | None = None,
    source: str | None = None,
    booking_id: int | None = None,
):
    qs = (
        BookingAuditEntry.objects.filter(action__in=SINGLE_ACTIONS)
        .select_related("booking", "user")
        .exclude(changes__has_key="import_batch_id")
    )
    if booking_id is not None:
        qs = qs.filter(booking_id=booking_id)
    if source:
        if source == "mass_import":
            qs = qs.filter(changes__source__in=MASS_IMPORT_SOURCES)
        else:
            qs = qs.filter(changes__source=source)
    if allowed_ports is not None:
        qs = qs.filter(
            Q(port_id__in=allowed_ports) | Q(booking__port_id__in=allowed_ports)
        )
    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lte=date_to)
    if actor_system:
        qs = qs.filter(user__isnull=True)
    elif actor_user_id is not None:
        qs = qs.filter(user_id=actor_user_id)
    return qs.order_by("-created_at")


def _batch_queryset(
    *,
    allowed_ports: list[int] | None,
    user,
    date_from,
    date_to,
    actor_system: bool = False,
    actor_user_id: int | None = None,
    kind: str | None = None,
):
    qs = BookingImportBatch.objects.select_related("created_by")
    if kind == "berthing_import":
        qs = qs.filter(label__startswith="BERTHING PAPERS")
    elif kind == "mass_import":
        qs = qs.exclude(label__startswith="BERTHING PAPERS")
    if allowed_ports is not None:
        qs = qs.filter(created_by=user)
    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lte=date_to)
    if actor_system:
        qs = qs.filter(created_by__isnull=True)
    elif actor_user_id is not None:
        qs = qs.filter(created_by_id=actor_user_id)
    return qs.order_by("-created_at")


def list_booking_activity_actors(
    *,
    user,
    allowed_ports: list[int] | None,
) -> dict[str, Any]:
    """Users that appear as actors in booking history the caller can see."""
    audit_qs = BookingAuditEntry.objects.filter(action__in=SINGLE_ACTIONS).exclude(
        changes__has_key="import_batch_id"
    )
    if allowed_ports is not None:
        audit_qs = audit_qs.filter(
            Q(port_id__in=allowed_ports) | Q(booking__port_id__in=allowed_ports)
        )
    audit_ids = set(
        audit_qs.exclude(user_id=None).values_list("user_id", flat=True).distinct()
    )
    has_system_audit = audit_qs.filter(user_id__isnull=True).exists()

    batch_qs = BookingImportBatch.objects.all()
    if allowed_ports is not None:
        batch_qs = batch_qs.filter(created_by=user)
    batch_ids = set(
        batch_qs.exclude(created_by_id=None)
        .values_list("created_by_id", flat=True)
        .distinct()
    )
    has_system_batch = batch_qs.filter(created_by_id__isnull=True).exists()

    return {
        "results": actor_options_from_ids(audit_ids | batch_ids),
        "has_system": has_system_audit or has_system_batch,
    }


def build_booking_activity(
    *,
    user,
    allowed_ports: list[int] | None,
    kind: str = "all",
    date_from: str | None = None,
    date_to: str | None = None,
    actor: str | None = None,
    booking_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    kind = (kind or "all").lower()
    if kind not in ACTIVITY_KINDS:
        kind = "all"

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    bound_from = _parse_bound(date_from)
    bound_to = _parse_bound(date_to, end_of_day=True)
    actor_system, actor_user_id = parse_actor_param(actor)

    if booking_id is not None:
        qs = _audit_queryset(
            allowed_ports=allowed_ports,
            date_from=bound_from,
            date_to=bound_to,
            actor_system=actor_system,
            actor_user_id=actor_user_id,
            booking_id=booking_id,
        )
        count = qs.count()
        start = (page - 1) * page_size
        rows = list(qs[start : start + page_size])
        return {
            "count": count,
            "page": page,
            "page_size": page_size,
            "results": [_single_item(entry) for entry in rows],
        }

    items: list[dict[str, Any]] = []
    include_single = kind in ("all", "single", "wizard", "berthing_import", "lta_generate")
    include_bulk = kind in ("all", "bulk", "mass_import", "berthing_import")
    source_filter = (
        kind if kind in ("wizard", "berthing_import", "lta_generate") else None
    )
    batch_kind = (
        "berthing_import"
        if kind == "berthing_import"
        else ("mass_import" if kind == "mass_import" else None)
    )

    if include_single:
        for entry in _audit_queryset(
            allowed_ports=allowed_ports,
            date_from=bound_from,
            date_to=bound_to,
            actor_system=actor_system,
            actor_user_id=actor_user_id,
            source=source_filter,
        )[:500]:
            items.append(_single_item(entry))

    if include_bulk:
        for batch in _batch_queryset(
            allowed_ports=allowed_ports,
            user=user,
            date_from=bound_from,
            date_to=bound_to,
            actor_system=actor_system,
            actor_user_id=actor_user_id,
            kind=batch_kind,
        )[:500]:
            items.append(_bulk_item(batch))

    items.sort(key=lambda x: x["occurred_at"], reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    return {
        "count": total,
        "page": page,
        "page_size": page_size,
        "results": page_items,
    }


def build_import_batch_detail(
    batch: BookingImportBatch,
    *,
    allowed_ports: list[int] | None,
) -> dict[str, Any]:
    bookings_qs = Booking.objects.filter(id__in=batch.created_booking_ids).only(
        "id",
        "booking_code",
        "port_id",
    )
    if allowed_ports is not None:
        bookings_qs = bookings_qs.filter(port_id__in=allowed_ports)

    created = [
        {"id": b.id, "booking_code": b.booking_code}
        for b in bookings_qs.order_by("booking_code")
    ]

    return {
        "id": batch.id,
        "label": batch.label,
        "source": batch.source,
        "status": batch.status,
        "created_at": batch.created_at,
        "finished_at": batch.finished_at,
        "user_display": _user_display(batch.created_by),
        "requested_count": batch.requested_count,
        "created_count": batch.created_count,
        "failed_count": batch.failed_count,
        "not_created_count": max(
            0, len(batch.retry_rows or []) - batch.failed_count
        ),
        "created": created,
        "failures": batch.failures or [],
        "retry_rows": batch.retry_rows or [],
        "retry_count": len(batch.retry_rows or []),
    }
