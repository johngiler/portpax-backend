"""Shared helpers for structured operational report exports."""

from __future__ import annotations

from datetime import date

from django.db.models import Q
from django.utils import timezone

from apps.bookings.constants import (
    ACTIVE_BOOKING_STATUSES,
    OCCUPATION_CONFLICT_STATUSES,
)
from apps.bookings.models import Booking, BookingStatus

PAX_BASIS_PLANNED = "planned"
PAX_BASIS_CAPACITY = "capacity"
PAX_BASIS_CHOICES = frozenset({PAX_BASIS_PLANNED, PAX_BASIS_CAPACITY})


def normalize_pax_basis(raw: str | None) -> str:
    value = (raw or PAX_BASIS_PLANNED).strip().lower()
    return value if value in PAX_BASIS_CHOICES else PAX_BASIS_PLANNED


def booking_pax(
    booking: Booking,
    *,
    pax_basis: str = PAX_BASIS_PLANNED,
) -> int:
    """
    Passenger contribution for matrix reports.

    Always prefer actual_pax when set (manifested Real).
    Otherwise: planned snapshot, or vessel max capacity per pax_basis.
    """
    if booking.actual_pax is not None:
        return int(booking.actual_pax)
    basis = normalize_pax_basis(pax_basis)
    if basis == PAX_BASIS_CAPACITY:
        vessel = getattr(booking, "vessel", None)
        cap = getattr(vessel, "pax_capacity", None) if vessel is not None else None
        return int(cap) if cap is not None else 0
    if booking.planned_pax is not None:
        return int(booking.planned_pax)
    return 0


def pax_basis_note(pax_basis: str) -> str:
    if normalize_pax_basis(pax_basis) == PAX_BASIS_CAPACITY:
        return (
            "Calls = escalas. PAX = real si existe, si no capacidad máxima del barco."
        )
    return (
        "Calls = escalas. PAX = real si existe, si no planificado "
        "(promedio de reales del barco hasta el último manifiesto)."
    )


def scheduled_bookings_qs(
    *,
    date_from: date,
    date_to: date,
    port_id: int | None = None,
    shipping_line_id: int | None = None,
    vessel_id: int | None = None,
    position_id: int | None = None,
    allowed_ports: set[int] | None = None,
    status: str | None = None,
    without_lta: bool = False,
):
    """Bookings for occupancy / availability reports.

    Default (no status): occupancy set (excludes cancelled).
    Optional status mirrors list filters: real codes, completed, action.
    """
    qs = Booking.objects.filter(
        call_date__gte=date_from,
        call_date__lte=date_to,
    ).select_related("port", "shipping_line", "vessel", "position")  # vessel needed for LOA/PAX
    if status == "completed":
        qs = qs.filter(
            Q(
                call_date__lt=timezone.localdate(),
                status__in=ACTIVE_BOOKING_STATUSES,
            )
            | Q(status=BookingStatus.R)
        )
    elif status == "action":
        qs = qs.filter(
            status__in=[BookingStatus.NR, BookingStatus.H],
            call_date__gte=timezone.localdate(),
        )
    elif status:
        qs = qs.filter(status=status)
    else:
        qs = qs.filter(status__in=OCCUPATION_CONFLICT_STATUSES)
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    if port_id:
        qs = qs.filter(port_id=port_id)
    if shipping_line_id:
        qs = qs.filter(shipping_line_id=shipping_line_id)
    if vessel_id:
        qs = qs.filter(vessel_id=vessel_id)
    if position_id:
        qs = qs.filter(position_id=position_id)
    if without_lta:
        qs = qs.exclude(
            status__in=[BookingStatus.LTA, BookingStatus.CL, BookingStatus.LTD],
        )
    return qs


def years_in_range(date_from: date, date_to: date) -> list[int]:
    return list(range(date_from.year, date_to.year + 1))
