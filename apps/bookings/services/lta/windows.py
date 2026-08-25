"""Seasonal booking windows (6-month blockcitos) for LTA vs open booking.

ITM seasons:
- Summer: 1 May → 31 Oct
- Winter: 1 Nov → 30 Apr (next calendar year)

Rolling blockcito model (Herman / Fernanda):
- Current period: 2 blocks (the block containing today + the previous one)
- Next 3 blocks: open booking (all carriers, no LTA preference)
- Following blocks: LTA zone (LTA holders only; slot preference applies)

Example if today is in Summer 2026:
- Current: Winter 2025/2026 + Summer 2026
- Open: Winter 2026/2027 … (3 blocks)
- LTA: from the block after open onward
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

# Período actual spans this many consecutive 6-month blocks ending at today's block.
CURRENT_BLOCKS = 2
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


def previous_block(
    season: SeasonKind,
    block_start: date,
) -> tuple[SeasonKind, date, date]:
    """Block immediately before the one starting at ``block_start``."""
    if season == SeasonKind.WINTER:
        y = block_start.year
        return SeasonKind.SUMMER, date(y, 5, 1), date(y, 10, 31)
    y = block_start.year
    return SeasonKind.WINTER, date(y - 1, 11, 1), date(y, 4, 30)


def window_start_block(today: date) -> tuple[SeasonKind, date, date]:
    """First block of the current period (``CURRENT_BLOCKS`` wide, ending at today)."""
    season, start, end = block_containing(today)
    for _ in range(max(0, CURRENT_BLOCKS - 1)):
        season, start, end = previous_block(season, start)
    return season, start, end


def season_block_label(season: SeasonKind, block_start: date) -> str:
    if season == SeasonKind.SUMMER:
        return f"Summer {block_start.year}"
    y = block_start.year
    return f"Winter {y}/{y + 1}"


def first_open_block_index() -> int:
    return CURRENT_BLOCKS


def first_lta_block_index(*, open_blocks: int = OPEN_BLOCKS_AFTER_CURRENT) -> int:
    return CURRENT_BLOCKS + open_blocks


def zone_for_block_index(
    index: int,
    *,
    lta_blocks: int = DEFAULT_LTA_BLOCKS,
    open_blocks: int = OPEN_BLOCKS_AFTER_CURRENT,
) -> BookingWindowZone:
    if index < 0:
        return BookingWindowZone.CURRENT
    if index < CURRENT_BLOCKS:
        return BookingWindowZone.CURRENT
    if index < CURRENT_BLOCKS + open_blocks:
        return BookingWindowZone.GENERAL
    if index < CURRENT_BLOCKS + open_blocks + lta_blocks:
        return BookingWindowZone.LTA_COVERED
    return BookingWindowZone.BEYOND


def block_index_for_date(call_date: date, today: date | None = None) -> int:
    """Block index relative to the current-period window start (0 = first current)."""
    today = today or date.today()
    season, start, end = window_start_block(today)
    if call_date < start:
        return -1
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
    open_blocks: int = OPEN_BLOCKS_AFTER_CURRENT,
) -> list[SeasonBlock]:
    """Enumerate blocks starting at the first current-period block."""
    today = today or date.today()
    total = (
        count
        if count is not None
        else CURRENT_BLOCKS + open_blocks + lta_blocks
    )
    season, start, end = window_start_block(today)
    blocks: list[SeasonBlock] = []
    for idx in range(total):
        zone = zone_for_block_index(
            idx, lta_blocks=lta_blocks, open_blocks=open_blocks
        )
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
    block_count = CURRENT_BLOCKS + open_blocks + lta_blocks
    blocks = list_season_blocks(
        today, count=block_count, lta_blocks=lta_blocks, open_blocks=open_blocks
    )
    current_last = blocks[CURRENT_BLOCKS - 1]
    open_last = blocks[CURRENT_BLOCKS + open_blocks - 1]
    lta_first = blocks[CURRENT_BLOCKS + open_blocks]
    lta_last = blocks[CURRENT_BLOCKS + open_blocks + lta_blocks - 1]
    return SeasonalWindows(
        reference_date=today,
        current_from=blocks[0].date_from,
        current_to=current_last.date_to,
        general_from=blocks[CURRENT_BLOCKS].date_from,
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
        "current_blocks": CURRENT_BLOCKS,
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
    """Current period span (``CURRENT_BLOCKS`` consecutive seasons)."""
    today = today or date.today()
    windows = compute_seasonal_windows(today)
    return windows.current_from, windows.current_to
