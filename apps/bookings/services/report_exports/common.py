"""Shared helpers for structured operational report exports."""

from __future__ import annotations

from datetime import date

from django.db.models import F, IntegerField, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.bookings.constants import (
    ACTIVE_BOOKING_STATUSES,
    OCCUPATION_CONFLICT_STATUSES,
)
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.booking.viewer_scope import clamp_viewer_open_market_range

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


def booking_pax_sum_expr(pax_basis: str = PAX_BASIS_PLANNED):
    """ORM twin of booking_pax() for list/dashboard aggregates."""
    if normalize_pax_basis(pax_basis) == PAX_BASIS_CAPACITY:
        projected = Coalesce(
            F("vessel__pax_capacity"), 0, output_field=IntegerField()
        )
    else:
        projected = Coalesce(F("planned_pax"), 0, output_field=IntegerField())
    return Coalesce(F("actual_pax"), projected, output_field=IntegerField())


def pax_basis_note(pax_basis: str) -> str:
    if normalize_pax_basis(pax_basis) == PAX_BASIS_CAPACITY:
        return (
            "Calls = escalas. PAX = real si existe, si no capacidad máxima del barco."
        )
    return (
        "Calls = escalas. PAX = real si existe, si no planificado "
        "(promedio de reales del barco hasta el último manifiesto)."
    )


def _merge_id_filters(
    single: int | None,
    many: list[int] | None,
) -> list[int]:
    out: list[int] = []
    for value in many or []:
        if value and value not in out:
            out.append(value)
    if single and single not in out:
        out.append(single)
    return out


def scheduled_bookings_qs(
    *,
    date_from: date,
    date_to: date,
    port_id: int | None = None,
    shipping_line_id: int | None = None,
    shipping_line_ids: list[int] | None = None,
    shipping_line_group_id: int | None = None,
    shipping_line_group_ids: list[int] | None = None,
    vessel_id: int | None = None,
    position_id: int | None = None,
    allowed_ports: set[int] | None = None,
    status: str | None = None,
    without_lta: bool = False,
    include_cancelled: bool = False,
    user=None,
    request=None,
):
    """Bookings for occupancy / availability reports.

    Default (no status): occupancy set (excludes cancelled).
    Optional status mirrors list filters: real codes, completed, action.
    ``include_cancelled`` adds Cancelada to the default occupancy set
    (e.g. tag-filtered movement summary of cancelled cohorts).
    """
    actor = user if user is not None else getattr(request, "user", None)
    date_from, date_to = clamp_viewer_open_market_range(actor, date_from, date_to)
    if date_to < date_from:
        return Booking.objects.none()
    qs = Booking.objects.filter(
        call_date__gte=date_from,
        call_date__lte=date_to,
    ).select_related(
        "port", "shipping_line", "shipping_line__group", "vessel", "position"
    )  # vessel needed for LOA/PAX; group for soft-focus
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
        statuses = list(OCCUPATION_CONFLICT_STATUSES)
        if include_cancelled:
            statuses.append(BookingStatus.C)
        qs = qs.filter(status__in=statuses)
    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)
    if port_id:
        qs = qs.filter(port_id=port_id)
    line_ids = _merge_id_filters(shipping_line_id, shipping_line_ids)
    group_ids = _merge_id_filters(shipping_line_group_id, shipping_line_group_ids)
    if vessel_id:
        qs = qs.filter(vessel_id=vessel_id)
    elif line_ids:
        qs = qs.filter(shipping_line_id__in=line_ids)
    elif group_ids:
        qs = qs.filter(shipping_line__group_id__in=group_ids)
    if position_id:
        qs = qs.filter(position_id=position_id)
    if without_lta:
        # Ghost LTA slots only; CL (confirmed) stays in the totals.
        qs = qs.exclude(status=BookingStatus.LTA)
    return qs


def years_in_range(date_from: date, date_to: date) -> list[int]:
    if date_to < date_from:
        return []
    return list(range(date_from.year, date_to.year + 1))


SEASON_NATURAL = "natural"
SEASON_SUMMER = "summer"
SEASON_WINTER = "winter"
SEASON_CHOICES = frozenset({SEASON_NATURAL, SEASON_SUMMER, SEASON_WINTER})


def normalize_season(raw: str | None) -> str:
    value = (raw or SEASON_NATURAL).strip().lower()
    return value if value in SEASON_CHOICES else SEASON_NATURAL


def call_date_in_season(call_date: date, season: str) -> bool:
    """
    Calendar season filter (same windows as bookings annual calendar).
    Summer: May–Oct. Winter: Nov–Apr. Natural: all months.
    """
    kind = normalize_season(season)
    if kind == SEASON_SUMMER:
        return 5 <= call_date.month <= 10
    if kind == SEASON_WINTER:
        return call_date.month >= 11 or call_date.month <= 4
    return True
