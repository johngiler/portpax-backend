"""Season / natural-year column periods for Panorama Navieras."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from apps.bookings.services.report_exports.common import (
    SEASON_NATURAL,
    SEASON_SUMMER,
    SEASON_WINTER,
    normalize_season,
    years_in_range,
)

# Matrix axis: calendar years vs Summer/Winter season windows in the range.
SEASON_AXIS_SEASONS = "seasons"


@dataclass(frozen=True, slots=True)
class MatrixPeriod:
    key: str
    kind: str
    year: int
    label: str
    start: date
    end: date

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def as_dict(self) -> dict[str, str | int]:
        return {
            "key": self.key,
            "kind": self.kind,
            "year": self.year,
            "label": self.label,
            "date_from": self.start.isoformat(),
            "date_to": self.end.isoformat(),
        }


def normalize_panorama_season(raw: str | None) -> str:
    """
    Panorama axis mode.

    - natural: one column per calendar year
    - seasons: Summer + Winter columns intersecting the range
    - summer / winter (legacy): only that season kind as columns
    """
    value = (raw or SEASON_NATURAL).strip().lower()
    if value == SEASON_AXIS_SEASONS:
        return SEASON_AXIS_SEASONS
    return normalize_season(value)


def _ranges_overlap(a0: date, a1: date, b0: date, b1: date) -> bool:
    return a0 <= b1 and b0 <= a1


def _clip(start: date, end: date, date_from: date, date_to: date) -> tuple[date, date]:
    return (max(start, date_from), min(end, date_to))


def summer_period(year: int) -> MatrixPeriod:
    return MatrixPeriod(
        key=f"summer-{year}",
        kind=SEASON_SUMMER,
        year=year,
        label=f"Summer {year}",
        start=date(year, 5, 1),
        end=date(year, 10, 31),
    )


def winter_period(start_year: int) -> MatrixPeriod:
    return MatrixPeriod(
        key=f"winter-{start_year}",
        kind=SEASON_WINTER,
        year=start_year,
        label=f"Winter {start_year}/{start_year + 1}",
        start=date(start_year, 11, 1),
        end=date(start_year + 1, 4, 30),
    )


def natural_year_period(year: int) -> MatrixPeriod:
    return MatrixPeriod(
        key=f"year-{year}",
        kind=SEASON_NATURAL,
        year=year,
        label=str(year),
        start=date(year, 1, 1),
        end=date(year, 12, 31),
    )


def matrix_periods_for_range(
    date_from: date,
    date_to: date,
    season: str,
) -> list[MatrixPeriod]:
    """
    Column periods for the selected axis that intersect [date_from, date_to].

    Period bounds are clipped to the report range so labels stay season-named
    while counts only include days inside the filter.
    """
    if date_from > date_to:
        return []

    axis = normalize_panorama_season(season)
    if axis == SEASON_NATURAL:
        out: list[MatrixPeriod] = []
        for year in years_in_range(date_from, date_to):
            period = natural_year_period(year)
            start, end = _clip(period.start, period.end, date_from, date_to)
            out.append(
                MatrixPeriod(
                    key=period.key,
                    kind=period.kind,
                    year=period.year,
                    label=period.label,
                    start=start,
                    end=end,
                )
            )
        return out

    kinds: tuple[str, ...]
    if axis == SEASON_SUMMER:
        kinds = (SEASON_SUMMER,)
    elif axis == SEASON_WINTER:
        kinds = (SEASON_WINTER,)
    else:
        kinds = (SEASON_SUMMER, SEASON_WINTER)

    candidates: list[MatrixPeriod] = []
    for year in range(date_from.year - 1, date_to.year + 1):
        if SEASON_SUMMER in kinds:
            candidates.append(summer_period(year))
        if SEASON_WINTER in kinds:
            candidates.append(winter_period(year))

    out = []
    for period in candidates:
        if not _ranges_overlap(period.start, period.end, date_from, date_to):
            continue
        start, end = _clip(period.start, period.end, date_from, date_to)
        out.append(
            MatrixPeriod(
                key=period.key,
                kind=period.kind,
                year=period.year,
                label=period.label,
                start=start,
                end=end,
            )
        )
    out.sort(key=lambda p: (p.start, p.kind, p.year))
    return out


def period_for_call_date(
    call_date: date,
    periods: list[MatrixPeriod],
) -> MatrixPeriod | None:
    for period in periods:
        if period.contains(call_date):
            return period
    return None
