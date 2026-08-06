"""Parse and apply booking list status query filters (multi-value)."""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.bookings.constants import ACTIVE_BOOKING_STATUSES
from apps.bookings.models import BookingStatus

# Real status codes + list-only virtual filters.
KNOWN_STATUS_FILTERS = frozenset(
    {
        *BookingStatus.values,
        "completed",
        "action",
    }
)


def parse_status_query_params(query_params) -> list[str]:
    """Accept repeated ?status= & comma lists (?status=h,co). Order preserved, deduped."""
    raw_values = list(query_params.getlist("status"))
    if not raw_values:
        single = query_params.get("status")
        if single:
            raw_values = [single]

    parsed: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for part in str(raw).split(","):
            code = part.strip().lower()
            if not code or code in seen:
                continue
            if code not in KNOWN_STATUS_FILTERS:
                continue
            seen.add(code)
            parsed.append(code)
    return parsed


def booking_status_filter_q(statuses: list[str]) -> Q | None:
    """OR of selected status filters. Empty list → no filter (caller skips)."""
    if not statuses:
        return None

    today = timezone.localdate()
    combined = Q()
    codes: list[str] = []
    for code in statuses:
        if code == "completed":
            combined |= Q(
                call_date__lt=today,
                status__in=ACTIVE_BOOKING_STATUSES,
            ) | Q(status=BookingStatus.R)
        elif code == "action":
            combined |= Q(
                status__in=[BookingStatus.NR, BookingStatus.H],
                call_date__gte=today,
            )
        else:
            codes.append(code)
    if codes:
        combined |= Q(status__in=codes)
    return combined


def apply_booking_status_filters(qs: QuerySet, statuses: list[str]) -> QuerySet:
    q = booking_status_filter_q(statuses)
    if q is None:
        return qs
    return qs.filter(q)
