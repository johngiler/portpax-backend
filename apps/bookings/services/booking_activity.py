"""Unified booking activity feed (single audits + mass import batches)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.audit.models import BookingAuditEntry
from apps.bookings.models import Booking, BookingImportBatch

SINGLE_ACTIONS = ("created", "operational_update", "status_change", "lta_linked")


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


def _audit_queryset(*, allowed_ports: list[int] | None, date_from, date_to):
    qs = (
        BookingAuditEntry.objects.filter(action__in=SINGLE_ACTIONS)
        .select_related("booking", "user")
        .exclude(changes__has_key="import_batch_id")
    )
    if allowed_ports is not None:
        from django.db.models import Q

        qs = qs.filter(
            Q(port_id__in=allowed_ports) | Q(booking__port_id__in=allowed_ports)
        )
    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lte=date_to)
    return qs.order_by("-created_at")


def _batch_queryset(*, allowed_ports: list[int] | None, user, date_from, date_to):
    qs = BookingImportBatch.objects.select_related("created_by")
    if allowed_ports is not None:
        qs = qs.filter(created_by=user)
    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lte=date_to)
    return qs.order_by("-created_at")


def build_booking_activity(
    *,
    user,
    allowed_ports: list[int] | None,
    kind: str = "all",
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    kind = (kind or "all").lower()
    if kind not in ("all", "single", "bulk"):
        kind = "all"

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    bound_from = _parse_bound(date_from)
    bound_to = _parse_bound(date_to, end_of_day=True)

    items: list[dict[str, Any]] = []

    if kind in ("all", "single"):
        for entry in _audit_queryset(
            allowed_ports=allowed_ports,
            date_from=bound_from,
            date_to=bound_to,
        )[:500]:
            items.append(_single_item(entry))

    if kind in ("all", "bulk"):
        for batch in _batch_queryset(
            allowed_ports=allowed_ports,
            user=user,
            date_from=bound_from,
            date_to=bound_to,
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
