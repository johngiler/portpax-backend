"""Shared helpers for structured operational report exports."""

from __future__ import annotations

from datetime import date

from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
from apps.bookings.models import Booking


def booking_pax(booking: Booking) -> int:
    """Prefer actual PAX when present; otherwise planned."""
    if booking.actual_pax is not None:
        return int(booking.actual_pax)
    if booking.planned_pax is not None:
        return int(booking.planned_pax)
    return 0


def scheduled_bookings_qs(
    *,
    date_from: date,
    date_to: date,
    port_id: int | None = None,
    shipping_line_id: int | None = None,
    allowed_ports: set[int] | None = None,
):
    """Bookings that count toward occupancy / PAX reports (excludes cancelled)."""
    qs = Booking.objects.filter(
        call_date__gte=date_from,
        call_date__lte=date_to,
        status__in=OCCUPATION_CONFLICT_STATUSES,
    ).select_related("port", "shipping_line", "vessel", "position")  # vessel needed for LOA/PAX
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    if port_id:
        qs = qs.filter(port_id=port_id)
    if shipping_line_id:
        qs = qs.filter(shipping_line_id=shipping_line_id)
    return qs


def years_in_range(date_from: date, date_to: date) -> list[int]:
    return list(range(date_from.year, date_to.year + 1))
