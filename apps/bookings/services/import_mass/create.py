"""Create bookings from resolved ITM mass-import rows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

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


def create_from_resolved_rows(
    rows: list[dict[str, Any]],
    *,
    created_by=None,
) -> dict[str, Any]:
    """
    Create one booking per selected resolved row.
    Continues on per-row errors; returns created + failures.
    """
    created: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for row in rows:
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
            )
            booking = bookings[0]
            created.append(
                {
                    "id": row_id,
                    "booking_id": booking.id,
                    "booking_code": booking.booking_code,
                }
            )
        except (KeyError, TypeError, ValueError, BookingBatchCreateError) as exc:
            failures.append(
                {
                    "id": row_id,
                    "detail": str(exc),
                }
            )

    return {
        "created_count": len(created),
        "failed_count": len(failures),
        "created": created,
        "failures": failures,
    }
