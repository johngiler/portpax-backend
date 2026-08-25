"""Per-agreement booking horizon policy (standard vs RCI staggered)."""

from __future__ import annotations

from datetime import date

from apps.bookings.models import LongTermAgreement
from apps.bookings.services.lta.windows import (
    block_containing,
    block_index_for_date,
    first_lta_block_index,
    season_for_date,
    SeasonKind,
)


def agreement_allows_horizon(
    agreement: LongTermAgreement,
    call_date: date,
    today: date | None = None,
) -> bool:
    """
    Whether ``call_date`` falls within this agreement's bookable blockcito horizon.

    Current + open blocks are always allowed when other match rules pass.
    In the LTA zone, depth and booking_policy apply.
    """
    today = today or date.today()
    idx = block_index_for_date(call_date, today)
    first_lta = first_lta_block_index()
    if idx < first_lta:
        return True

    lta_slot = idx - first_lta
    depth = max(1, int(agreement.lta_depth_blocks or 2))
    if lta_slot >= depth:
        return False

    policy = agreement.booking_policy or LongTermAgreement.BookingPolicy.STANDARD
    if policy == LongTermAgreement.BookingPolicy.STANDARD:
        return True

    return _rci_staggered_allows(agreement, call_date, today, idx)


def _rci_staggered_allows(
    agreement: LongTermAgreement,
    call_date: date,
    today: date,
    block_idx: int,
) -> bool:
    """RCI-style: stabilization year then Summer↔Winter alternation in LTA zone."""
    first_lta = first_lta_block_index()
    if block_idx < first_lta:
        return True

    call_season = season_for_date(call_date)
    today_season = season_for_date(today)

    if _in_stabilization_year(agreement, today):
        # First year: may take up to 3 consecutive LTA blocks.
        return first_lta <= block_idx <= first_lta + 2

    if today_season == SeasonKind.SUMMER:
        return call_season == SeasonKind.WINTER
    return call_season == SeasonKind.SUMMER


def _in_stabilization_year(agreement: LongTermAgreement, today: date) -> bool:
    """
    Stabilization = first 12 months from the agreement's start block.

    Uses valid_from when set; otherwise treats today as still stabilizing.
    """
    anchor = agreement.valid_from or today
    _, anchor_start, _ = block_containing(anchor)
    months = (today.year - anchor_start.year) * 12 + (today.month - anchor_start.month)
    if today.day < anchor_start.day:
        months -= 1
    return months < 12
