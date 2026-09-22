"""Primer arribo — earliest CO/CL/R booking per vessel + port."""

from __future__ import annotations

from apps.bookings.models import Booking, BookingStatus

FIRST_ARRIVAL_STATUSES = frozenset(
    {
        BookingStatus.CO,
        BookingStatus.CL,
        BookingStatus.R,
    }
)


def recalculate_first_arrival(*, vessel_id: int, port_id: int) -> None:
    """
    For one vessel+port pair: clear all flags, then mark the earliest
    CO/CL/R booking (by call_date, then id) as first_arrival=True.
    If none count, all remain False.
    """
    if not vessel_id or not port_id:
        return
    qs = Booking.objects.filter(vessel_id=vessel_id, port_id=port_id)
    qs.filter(first_arrival=True).update(first_arrival=False)
    first_id = (
        qs.filter(status__in=FIRST_ARRIVAL_STATUSES)
        .order_by("call_date", "id")
        .values_list("id", flat=True)
        .first()
    )
    if first_id:
        Booking.objects.filter(pk=first_id).update(first_arrival=True)


def recalculate_first_arrival_for_pairs(
    pairs: set[tuple[int, int]],
) -> None:
    for vessel_id, port_id in pairs:
        if vessel_id and port_id:
            recalculate_first_arrival(vessel_id=vessel_id, port_id=port_id)


def recalculate_first_arrival_for_booking(
    booking: Booking,
    *,
    previous_vessel_id: int | None = None,
    previous_port_id: int | None = None,
) -> None:
    """Recalculate current pair and any previous vessel/port after a move."""
    pairs: set[tuple[int, int]] = {(booking.vessel_id, booking.port_id)}
    prev_v = previous_vessel_id if previous_vessel_id else booking.vessel_id
    prev_p = previous_port_id if previous_port_id else booking.port_id
    if previous_vessel_id is not None or previous_port_id is not None:
        pairs.add((prev_v, prev_p))
    recalculate_first_arrival_for_pairs(pairs)


def backfill_all_first_arrivals() -> int:
    """Recompute every distinct vessel+port pair. Returns pair count."""
    pairs = (
        Booking.objects.order_by()
        .values_list("vessel_id", "port_id")
        .distinct()
    )
    count = 0
    for vessel_id, port_id in pairs:
        recalculate_first_arrival(vessel_id=vessel_id, port_id=port_id)
        count += 1
    return count
