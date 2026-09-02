"""Compute expected (planned) PAX from vessel history or max capacity."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Avg
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.catalogs.models import Vessel


@dataclass(frozen=True)
class PlannedPaxSuggestion:
    planned_pax: int | None
    capacity: int | None
    sample_count: int
    source: str  # "average" | "capacity" | "none"
    pct_of_capacity: int | None


def _pct(part: int | None, whole: int | None) -> int | None:
    if part is None or whole is None or whole <= 0:
        return None
    return int(round((part / whole) * 100))


def _history_actual_qs(
    vessel_id: int,
    *,
    exclude_booking_id: int | None = None,
    as_of=None,
):
    """
    Manifested PAX history for a vessel up to `as_of` (default: today).

    Future calls have no actual_pax; this also excludes any row dated after as_of.
    """
    if as_of is None:
        as_of = timezone.localdate()
    qs = Booking.objects.filter(
        vessel_id=vessel_id,
        actual_pax__isnull=False,
        call_date__lte=as_of,
    ).exclude(status=BookingStatus.C)
    if exclude_booking_id is not None:
        qs = qs.exclude(pk=exclude_booking_id)
    return qs


def compute_planned_pax_for_vessel(
    vessel_id: int,
    *,
    exclude_booking_id: int | None = None,
    as_of=None,
) -> PlannedPaxSuggestion:
    """
    Tentative PAX for future calls of this vessel.

    = round(AVG(actual_pax)) over the full Real history up to the latest past
      call (as_of / “yesterday’s” snapshot inclusive) — not only the last value.
    No history yet → vessel max capacity.
    """
    try:
        vessel = Vessel.objects.only("id", "pax_capacity").get(pk=vessel_id)
    except Vessel.DoesNotExist:
        return PlannedPaxSuggestion(
            planned_pax=None,
            capacity=None,
            sample_count=0,
            source="none",
            pct_of_capacity=None,
        )

    capacity = vessel.pax_capacity
    qs = _history_actual_qs(
        vessel_id,
        exclude_booking_id=exclude_booking_id,
        as_of=as_of,
    )

    sample_count = qs.count()
    if sample_count == 0:
        planned = int(capacity) if capacity is not None else None
        return PlannedPaxSuggestion(
            planned_pax=planned,
            capacity=capacity,
            sample_count=0,
            source="capacity" if planned is not None else "none",
            pct_of_capacity=_pct(planned, capacity),
        )

    avg = qs.aggregate(avg=Avg("actual_pax"))["avg"]
    planned = int(round(avg)) if avg is not None else None
    return PlannedPaxSuggestion(
        planned_pax=planned,
        capacity=capacity,
        sample_count=sample_count,
        source="average",
        pct_of_capacity=_pct(planned, capacity),
    )


def recompute_real_planned_pax_chronological(
    *,
    vessel_id: int | None = None,
) -> int:
    """
    Rebuild planned_pax for Real bookings from prior actual history.

    For each Real row: planned = AVG(actuals of earlier calls) or capacity
    if none yet (same rule as create-time snapshot, as-of that call_date).
    """
    vessel_qs = Vessel.objects.only("id", "pax_capacity")
    if vessel_id is not None:
        vessel_qs = vessel_qs.filter(pk=vessel_id)

    updated = 0
    for vessel in vessel_qs.iterator():
        capacity = (
            int(vessel.pax_capacity) if vessel.pax_capacity is not None else None
        )
        history_sum = 0
        history_count = 0
        bookings = (
            Booking.objects.filter(
                vessel_id=vessel.id,
                actual_pax__isnull=False,
            )
            .exclude(status=BookingStatus.C)
            .order_by("call_date", "id")
            .only("id", "status", "planned_pax", "actual_pax")
        )
        to_update: list[Booking] = []
        for booking in bookings.iterator():
            if booking.status == BookingStatus.R:
                if history_count > 0:
                    planned = int(round(history_sum / history_count))
                else:
                    planned = capacity
                if planned is not None and booking.planned_pax != planned:
                    booking.planned_pax = planned
                    to_update.append(booking)
            history_sum += int(booking.actual_pax)
            history_count += 1
        if to_update:
            Booking.objects.bulk_update(to_update, ["planned_pax"], batch_size=500)
            updated += len(to_update)
    return updated


def recompute_future_planned_pax_from_history(
    *,
    vessel_id: int | None = None,
    as_of=None,
) -> int:
    """
    Set planned_pax on future (non-cancelled) bookings from the vessel average
    of manifested actual_pax up to as_of (default today). No history → capacity.
    """
    if as_of is None:
        as_of = timezone.localdate()

    vessel_qs = Vessel.objects.only("id", "pax_capacity")
    if vessel_id is not None:
        vessel_qs = vessel_qs.filter(pk=vessel_id)

    updated = 0
    for vessel in vessel_qs.iterator():
        suggestion = compute_planned_pax_for_vessel(vessel.id, as_of=as_of)
        planned = suggestion.planned_pax
        if planned is None:
            continue
        qs = (
            Booking.objects.filter(vessel_id=vessel.id, call_date__gte=as_of)
            .exclude(status=BookingStatus.C)
            .filter(actual_pax__isnull=True)
            .exclude(planned_pax=planned)
        )
        n = qs.update(planned_pax=planned)
        updated += n
    return updated
