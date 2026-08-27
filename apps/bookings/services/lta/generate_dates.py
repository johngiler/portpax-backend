"""Candidate call dates for LTA materialization (Fase C — A1 zone only)."""

from __future__ import annotations

from datetime import date, timedelta

from apps.bookings.models import LongTermAgreement
from apps.bookings.services.lta.matching import (
    agreement_covers_cadence,
    agreement_covers_validity,
    agreement_covers_weekday,
)
from apps.bookings.services.lta.policy import agreement_allows_horizon
from apps.bookings.services.lta.windows import (
    block_index_for_date,
    compute_seasonal_windows,
    first_lta_block_index,
)


def agreement_in_lta_zone_only(
    agreement: LongTermAgreement,
    call_date: date,
    today: date | None = None,
) -> bool:
    """A1: only seasonal LTA-covered blocks for this agreement's depth (not current/open)."""
    today = today or date.today()
    idx = block_index_for_date(call_date, today)
    if idx < first_lta_block_index():
        return False
    return agreement_allows_horizon(agreement, call_date, today)


def lta_zone_date_bounds(
    agreement: LongTermAgreement,
    today: date | None = None,
) -> tuple[date, date] | None:
    """Inclusive [start, end] for this agreement's LTA zone ∩ validity."""
    today = today or date.today()
    depth = max(1, int(agreement.lta_depth_blocks or 2))
    windows = compute_seasonal_windows(today, lta_blocks=depth)
    start = windows.lta_from
    end = windows.lta_to
    if agreement.valid_from:
        start = max(start, agreement.valid_from)
    if agreement.valid_until:
        end = min(end, agreement.valid_until)
    if start > end:
        return None
    return start, end


def iter_agreement_candidate_dates(
    agreement: LongTermAgreement,
    today: date | None = None,
) -> list[date]:
    """
    Dates that match weekday + cadence + validity and fall in the A1 LTA zone.
    """
    today = today or date.today()
    bounds = lta_zone_date_bounds(agreement, today)
    if bounds is None:
        return []
    start, end = bounds

    interval = agreement.interval_days
    anchor = agreement.cadence_anchor
    if interval and anchor is not None:
        if anchor > end:
            return []
        # First grid date on/after start.
        if anchor >= start:
            cursor = anchor
        else:
            delta = (start - anchor).days
            steps = (delta + interval - 1) // interval
            cursor = anchor + timedelta(days=steps * interval)
        out: list[date] = []
        while cursor <= end:
            if (
                agreement_covers_validity(agreement, cursor)
                and agreement_covers_weekday(agreement, cursor)
                and agreement_covers_cadence(agreement, cursor)
                and agreement_in_lta_zone_only(agreement, cursor, today)
            ):
                out.append(cursor)
            cursor += timedelta(days=interval)
        return out

    out = []
    cursor = start
    one = timedelta(days=1)
    while cursor <= end:
        if (
            agreement_covers_validity(agreement, cursor)
            and agreement_covers_weekday(agreement, cursor)
            and agreement_in_lta_zone_only(agreement, cursor, today)
        ):
            out.append(cursor)
        cursor += one
    return out
