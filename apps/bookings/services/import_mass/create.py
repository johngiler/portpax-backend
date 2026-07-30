"""Create bookings from resolved ITM mass-import rows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.utils import timezone

from apps.bookings.models import BookingImportBatch
from apps.bookings.services.booking.batch_create import (
    BookingBatchCreateError,
    create_booking_batch,
)


def _parse_time(value: str | None):
    if not value:
        return None
    text = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _normalize_retry_row(
    row: dict[str, Any],
    *,
    extra_issues: list[str] | None = None,
) -> dict[str, Any]:
    """Normalize a preview/create row into a BulkImportPreviewRow-shaped snapshot."""
    row_id = str(row.get("id") or row.get("row_number") or "")
    try:
        row_number = int(row.get("row_number") or 0)
    except (TypeError, ValueError):
        row_number = 0

    issues = _as_str_list(row.get("issues"))
    if extra_issues:
        for issue in extra_issues:
            if issue and issue not in issues:
                issues.append(issue)

    call_date = row.get("call_date")
    eta = row.get("eta")
    etd = row.get("etd")

    port_id = row.get("port_id")
    vessel_id = row.get("vessel_id")
    shipping_line_id = row.get("shipping_line_id")
    try:
        port_id = int(port_id) if port_id is not None and port_id != "" else None
    except (TypeError, ValueError):
        port_id = None
    try:
        vessel_id = int(vessel_id) if vessel_id is not None and vessel_id != "" else None
    except (TypeError, ValueError):
        vessel_id = None
    try:
        shipping_line_id = (
            int(shipping_line_id)
            if shipping_line_id is not None and shipping_line_id != ""
            else None
        )
    except (TypeError, ValueError):
        shipping_line_id = None

    selectable = bool(row.get("selectable"))
    if issues:
        # Create failures or deferred invalid rows stay non-selectable until re-resolved.
        if extra_issues:
            selectable = False
    elif row.get("selectable") is None:
        selectable = bool(port_id and vessel_id and shipping_line_id and call_date and eta and etd)

    return {
        "id": row_id or f"retry-{row_number}",
        "row_number": row_number,
        "ship": str(row.get("ship") or row.get("vessel_name") or ""),
        "port_raw": str(row.get("port_raw") or row.get("port") or row.get("port_name") or ""),
        "vendor_name": str(row.get("vendor_name") or ""),
        "call_type": str(row.get("call_type") or ""),
        "call_date": str(call_date) if call_date else None,
        "eta": str(eta)[:8] if eta else None,
        "etd": str(etd)[:8] if etd else None,
        "port_id": port_id,
        "port_name": row.get("port_name"),
        "port_code": row.get("port_code"),
        "vessel_id": vessel_id,
        "vessel_name": row.get("vessel_name") or row.get("ship"),
        "shipping_line_id": shipping_line_id,
        "shipping_line_name": row.get("shipping_line_name"),
        "issues": issues,
        "warnings": _as_str_list(row.get("warnings")),
        "selectable": selectable,
        "selected_default": False,
    }


def _failure_payload(row: dict[str, Any], row_id: Any, detail: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "row_id": row_id,
        "detail": detail,
    }
    ship = row.get("ship") or row.get("vessel_name")
    port = row.get("port") or row.get("port_raw") or row.get("port_code") or row.get("port_name")
    call_date = row.get("call_date")
    if ship:
        payload["ship"] = str(ship)
    if port:
        payload["port"] = str(port)
    if call_date:
        payload["call_date"] = str(call_date)
    return payload


def create_from_resolved_rows(
    rows: list[dict[str, Any]],
    *,
    created_by=None,
    source: str = BookingImportBatch.Source.FILE,
    label: str = "",
    deferred_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Create one booking per selected resolved row.
    Persists a BookingImportBatch with successes, failures, and retry_rows
    (failed creates + deferred/not-selectable/not-selected preview rows).
    """
    if source not in BookingImportBatch.Source.values:
        source = BookingImportBatch.Source.FILE
    batch_label = (label or "").strip() or (
        "Pegado desde Excel"
        if source == BookingImportBatch.Source.PASTE
        else "Importación masiva"
    )

    deferred = deferred_rows or []
    batch = BookingImportBatch.objects.create(
        created_by=created_by,
        source=source,
        label=batch_label,
        requested_count=len(rows) + len(deferred),
        status=BookingImportBatch.Status.COMPLETED,
    )

    created: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    created_booking_ids: list[int] = []
    retry_rows: list[dict[str, Any]] = []
    audit_changes = {"import_batch_id": batch.id}

    for row in deferred:
        if isinstance(row, dict):
            retry_rows.append(_normalize_retry_row(row))

    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id") or row.get("row_number")
        try:
            port_id = int(row["port_id"])
            shipping_line_id = int(row["shipping_line_id"])
            vessel_id = int(row["vessel_id"])
            call_date = date.fromisoformat(str(row["call_date"]))
            eta = _parse_time(row.get("eta"))
            etd = _parse_time(row.get("etd"))
            if eta is None or etd is None:
                raise BookingBatchCreateError("ETA/ETD inválidos.", "eta")

            bookings = create_booking_batch(
                port_id=port_id,
                shipping_line_id=shipping_line_id,
                vessel_id=vessel_id,
                call_dates=[call_date],
                notes="",
                created_by=created_by,
                eta=eta,
                etd=etd,
                audit_changes=audit_changes,
            )
            booking = bookings[0]
            created_booking_ids.append(booking.id)
            created.append(
                {
                    "id": row_id,
                    "booking_id": booking.id,
                    "booking_code": booking.booking_code,
                }
            )
        except (KeyError, TypeError, ValueError, BookingBatchCreateError) as exc:
            detail = str(exc)
            failures.append(_failure_payload(row, row_id, detail))
            retry_rows.append(_normalize_retry_row(row, extra_issues=[detail]))

    batch.created_count = len(created)
    batch.failed_count = len(failures)
    batch.created_booking_ids = created_booking_ids
    batch.failures = failures
    batch.retry_rows = retry_rows
    batch.finished_at = timezone.now()
    batch.save(
        update_fields=[
            "created_count",
            "failed_count",
            "created_booking_ids",
            "failures",
            "retry_rows",
            "finished_at",
            "status",
            "requested_count",
        ]
    )

    return {
        "batch_id": batch.id,
        "created_count": len(created),
        "failed_count": len(failures),
        "created": created,
        "failures": failures,
        "retry_count": len(retry_rows),
    }
