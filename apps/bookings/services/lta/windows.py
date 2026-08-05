"""Seasonal booking windows (Winter / Summer) for LTA vs open booking.

ITM seasons (Especificaciones LTA / meet):
- Winter: 1 Nov → 30 Apr (next calendar year)
- Summer: 1 May → 31 Oct

Standard horizon (P1-style Gantt in Especificaciones):
- Current period: Winter + following Summer that contain ``today`` (12 months)
- General booking: 18 months after current ends (open market)
- LTA covered: 12 months after general ends (LTA holders only)

Example (today in Summer 2026):
- Current: 2025-11-01 … 2026-10-31
- General: 2026-11-01 … 2028-04-30
- LTA covered: 2028-05-01 … 2029-04-30
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from apps.bookings.services.lta.matching import add_months


class BookingWindowZone(str, Enum):
    CURRENT = "current"
    GENERAL = "general"
    LTA_COVERED = "lta_covered"
    BEYOND = "beyond"


@dataclass(frozen=True)
class SeasonalWindows:
    current_from: date
    current_to: date
    general_from: date
    general_to: date
    lta_from: date
    lta_to: date

    def zone_for(self, call_date: date) -> BookingWindowZone:
        if call_date < self.current_from:
            # Past relative to current window — ops already underway.
            return BookingWindowZone.CURRENT
        if call_date <= self.current_to:
            return BookingWindowZone.CURRENT
        if call_date <= self.general_to:
            return BookingWindowZone.GENERAL
        if call_date <= self.lta_to:
            return BookingWindowZone.LTA_COVERED
        return BookingWindowZone.BEYOND


def winter_bounds(winter_start_year: int) -> tuple[date, date]:
    """Winter starting 1 Nov ``winter_start_year`` → 30 Apr ``winter_start_year+1``."""
    return (
        date(winter_start_year, 11, 1),
        date(winter_start_year + 1, 4, 30),
    )


def summer_bounds(summer_year: int) -> tuple[date, date]:
    """Summer 1 May → 31 Oct of ``summer_year``."""
    return (date(summer_year, 5, 1), date(summer_year, 10, 31))


def current_period_bounds(today: date | None = None) -> tuple[date, date]:
    """
    12-month operating year: Winter + Summer that include ``today``.

    - May–Oct (Summer Y): Nov 1 (Y-1) … Oct 31 Y
    - Nov–Dec (start of Winter Y): Nov 1 Y … Oct 31 (Y+1)
    - Jan–Apr (rest of Winter Y-1): Nov 1 (Y-1) … Oct 31 Y
    """
    today = today or date.today()
    y, m = today.year, today.month
    if 5 <= m <= 10:
        return date(y - 1, 11, 1), date(y, 10, 31)
    if m >= 11:
        return date(y, 11, 1), date(y + 1, 10, 31)
    return date(y - 1, 11, 1), date(y, 10, 31)


def compute_seasonal_windows(
    today: date | None = None,
    *,
    general_months: int = 18,
    lta_covered_months: int = 12,
) -> SeasonalWindows:
    today = today or date.today()
    current_from, current_to = current_period_bounds(today)
    # Current always ends 31 Oct → general starts 1 Nov of that year.
    general_from = date(current_to.year, 11, 1)
    # Nov 1 + 18 months → May 1; last general day is Apr 30.
    general_to = add_months(general_from, general_months) - timedelta(days=1)
    lta_from = general_to + timedelta(days=1)
    lta_to = add_months(lta_from, lta_covered_months) - timedelta(days=1)
    return SeasonalWindows(
        current_from=current_from,
        current_to=current_to,
        general_from=general_from,
        general_to=general_to,
        lta_from=lta_from,
        lta_to=lta_to,
    )


def open_market_allows(call_date: date, today: date | None = None) -> bool:
    """Anyone may book in current + general zones."""
    zone = compute_seasonal_windows(today).zone_for(call_date)
    return zone in (BookingWindowZone.CURRENT, BookingWindowZone.GENERAL)


def lta_holder_allows(call_date: date, today: date | None = None) -> bool:
    """Matching LTA holders may book through LTA covered (inclusive)."""
    zone = compute_seasonal_windows(today).zone_for(call_date)
    return zone in (
        BookingWindowZone.CURRENT,
        BookingWindowZone.GENERAL,
        BookingWindowZone.LTA_COVERED,
    )
