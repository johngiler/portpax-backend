"""Seasonal booking windows (6-month blockcitos) for LTA vs open booking.

ITM seasons:
- Summer: 1 May → 31 Oct
- Winter: 1 Nov → 30 Apr (next calendar year)

Rolling blockcito model (Herman / Fernanda):
- B0: current 6-month block (contains today)
- B1–B3: open booking (all carriers, no LTA preference)
- B4+: LTA zone (LTA holders only; slot preference applies)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

OPEN_BLOCKS_AFTER_CURRENT = 3
DEFAULT_LTA_BLOCKS = 4


class SeasonKind(str, Enum):
    SUMMER = "summer"
    WINTER = "winter"


class BookingWindowZone(str, Enum):
    CURRENT = "current"
    GENERAL = "general"
    LTA_COVERED = "lta_covered"
    BEYOND = "beyond"


@dataclass(frozen=True)
class SeasonBlock:
    index: int
    season: SeasonKind
    label: str
    date_from: date
    date_to: date
    zone: BookingWindowZone


@dataclass(frozen=True)
class SeasonalWindows:
    reference_date: date
    current_from: date
    current_to: date
    general_from: date
    general_to: date
    lta_from: date
    lta_to: date
    blocks: tuple[SeasonBlock, ...]

    def zone_for(self, call_date: date) -> BookingWindowZone:
        idx = block_index_for_date(call_date, self.reference_date)
        return zone_for_block_index(idx, lta_blocks=DEFAULT_LTA_BLOCKS)


def block_containing(d: date) -> tuple[SeasonKind, date, date]:
    """Return (season, start, end) for the 6-month block containing ``d``."""
    y, m = d.year, d.month
    if 5 <= m <= 10:
        return SeasonKind.SUMMER, date(y, 5, 1), date(y, 10, 31)
    if m >= 11:
        return SeasonKind.WINTER, date(y, 11, 1), date(y + 1, 4, 30)
    return SeasonKind.WINTER, date(y - 1, 11, 1), date(y, 4, 30)


def next_block(
    season: SeasonKind,
    block_end: date,
) -> tuple[SeasonKind, date, date]:
    if season == SeasonKind.SUMMER:
        y = block_end.year
        return SeasonKind.WINTER, date(y, 11, 1), date(y + 1, 4, 30)
    y = block_end.year
    return SeasonKind.SUMMER, date(y, 5, 1), date(y, 10, 31)


def season_block_label(season: SeasonKind, block_start: date) -> str:
    if season == SeasonKind.SUMMER:
        return f"Summer {block_start.year}"
    y = block_start.year
    return f"Winter {y}/{y + 1}"


def zone_for_block_index(
    index: int,
    *,
    lta_blocks: int = DEFAULT_LTA_BLOCKS,
) -> BookingWindowZone:
    if index < 0:
        return BookingWindowZone.CURRENT
    if index == 0:
        return BookingWindowZone.CURRENT
    if index <= OPEN_BLOCKS_AFTER_CURRENT:
        return BookingWindowZone.GENERAL
    if index <= OPEN_BLOCKS_AFTER_CURRENT + lta_blocks:
        return BookingWindowZone.LTA_COVERED
    return BookingWindowZone.BEYOND


def block_index_for_date(call_date: date, today: date | None = None) -> int:
    """Block index relative to today's block (0 = current). Returns 999 if far future."""
    today = today or date.today()
    _, start, end = block_containing(today)
    if call_date < start:
        return -1
    season, start, end = block_containing(today)
    idx = 0
    while idx <= 120:
        if start <= call_date <= end:
            return idx
        season, start, end = next_block(season, end)
        idx += 1
    return 999


def season_for_date(d: date) -> SeasonKind:
    return block_containing(d)[0]


def list_season_blocks(
    today: date | None = None,
    *,
    count: int | None = None,
    lta_blocks: int = DEFAULT_LTA_BLOCKS,
) -> list[SeasonBlock]:
    """Enumerate blocks starting at today's block."""
    today = today or date.today()
    total = count if count is not None else OPEN_BLOCKS_AFTER_CURRENT + lta_blocks + 1
    season, start, end = block_containing(today)
    blocks: list[SeasonBlock] = []
    for idx in range(total):
        zone = zone_for_block_index(idx, lta_blocks=lta_blocks)
        blocks.append(
            SeasonBlock(
                index=idx,
                season=season,
                label=season_block_label(season, start),
                date_from=start,
                date_to=end,
                zone=zone,
            )
        )
        season, start, end = next_block(season, end)
    return blocks


def compute_seasonal_windows(
    today: date | None = None,
    *,
    open_blocks: int = OPEN_BLOCKS_AFTER_CURRENT,
    lta_blocks: int = DEFAULT_LTA_BLOCKS,
) -> SeasonalWindows:
    today = today or date.today()
    block_count = open_blocks + lta_blocks + 1
    blocks = list_season_blocks(today, count=block_count, lta_blocks=lta_blocks)
    current = blocks[0]
    open_last = blocks[open_blocks]
    lta_first = blocks[open_blocks + 1]
    lta_last = blocks[open_blocks + lta_blocks]
    return SeasonalWindows(
        reference_date=today,
        current_from=current.date_from,
        current_to=current.date_to,
        general_from=blocks[1].date_from,
        general_to=open_last.date_to,
        lta_from=lta_first.date_from,
        lta_to=lta_last.date_to,
        blocks=tuple(blocks),
    )


def windows_as_dict(today: date | None = None) -> dict:
    """JSON-serializable snapshot for API / calendar UI."""
    today = today or date.today()
    windows = compute_seasonal_windows(today)
    return {
        "reference_date": windows.reference_date.isoformat(),
        "current_from": windows.current_from.isoformat(),
        "current_to": windows.current_to.isoformat(),
        "general_from": windows.general_from.isoformat(),
        "general_to": windows.general_to.isoformat(),
        "lta_from": windows.lta_from.isoformat(),
        "lta_to": windows.lta_to.isoformat(),
        "open_blocks": OPEN_BLOCKS_AFTER_CURRENT,
        "blocks": [
            {
                "index": b.index,
                "season": b.season.value,
                "label": b.label,
                "date_from": b.date_from.isoformat(),
                "date_to": b.date_to.isoformat(),
                "zone": b.zone.value,
            }
            for b in windows.blocks
        ],
    }


def open_market_allows(call_date: date, today: date | None = None) -> bool:
    """Anyone may book in current + open booking blocks."""
    today = today or date.today()
    zone = compute_seasonal_windows(today).zone_for(call_date)
    return zone in (BookingWindowZone.CURRENT, BookingWindowZone.GENERAL)


def lta_holder_allows(call_date: date, today: date | None = None) -> bool:
    """Matching LTA holders may book through the global LTA covered horizon."""
    today = today or date.today()
    zone = compute_seasonal_windows(today).zone_for(call_date)
    return zone in (
        BookingWindowZone.CURRENT,
        BookingWindowZone.GENERAL,
        BookingWindowZone.LTA_COVERED,
    )


# Legacy helpers kept for imports elsewhere
def winter_bounds(winter_start_year: int) -> tuple[date, date]:
    return (
        date(winter_start_year, 11, 1),
        date(winter_start_year + 1, 4, 30),
    )


def summer_bounds(summer_year: int) -> tuple[date, date]:
    return (date(summer_year, 5, 1), date(summer_year, 10, 31))


def current_period_bounds(today: date | None = None) -> tuple[date, date]:
    """Current 6-month block (B0)."""
    today = today or date.today()
    _, start, end = block_containing(today)
    return start, end
