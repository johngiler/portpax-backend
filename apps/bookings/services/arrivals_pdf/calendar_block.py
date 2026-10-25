"""Beto-style month block: positions as rows, Sunday–Saturday as columns."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from apps.bookings.services.arrivals_pdf.labels import (
    MONTHS_SHORT,
    WEEKDAYS_CAL_SHORT,
    WEEKDAYS_WEEK_SHORT,
    month_title,
    week_title,
)
from apps.bookings.services.arrivals_pdf.month_grid import bookings_by_day, month_weeks
from apps.bookings.services.arrivals_pdf.occupancy import days_in_range, prepare_availability_layout

BLOCK_META_COLS = 2
DAYS = 7
BLOCK_COLS = BLOCK_META_COLS + DAYS


@dataclass(frozen=True)
class WeekBand:
    count: int
    dates: list[str]
    rows: list[tuple[str, list[str]]]


@dataclass(frozen=True)
class MonthBlock:
    year: int
    month: int
    title: str
    total: int
    labels: list[str]
    weeks: list[WeekBand]
    weekday_labels: tuple[str, ...] = WEEKDAYS_CAL_SHORT


def build_month_block(port, year: int, month: int, rows: list) -> MonthBlock:
    labels, pos_index, _counts = prepare_availability_layout(port, rows)
    by_day = bookings_by_day(rows)
    n_pos = max(len(labels), 1)
    weeks: list[WeekBand] = []
    for week in month_weeks(year, month):
        count = sum(len(by_day.get(day, [])) for day in week if day)
        dates = [_day_stamp(day) if day else "" for day in week]
        pos_rows: list[tuple[str, list[str]]] = []
        for index, label in enumerate(labels):
            cells: list[str] = []
            for day in week:
                if day is None:
                    cells.append("")
                    continue
                ships = [
                    booking
                    for booking in by_day.get(day, [])
                    if _slot_index(booking, pos_index, n_pos) == index
                ]
                cells.append(_ship_cell(ships) if ships else "0")
            pos_rows.append((label, cells))
        weeks.append(WeekBand(count=count, dates=dates, rows=pos_rows))
    return MonthBlock(
        year=year,
        month=month,
        title=month_title(year, month),
        total=len(rows),
        labels=labels,
        weeks=weeks,
        weekday_labels=WEEKDAYS_CAL_SHORT,
    )


def week_dates(date_from: date, date_to: date | None = None) -> list[date]:
    """Monday–Sunday week covering date_from (UI weekly calendar)."""
    if date_to is not None:
        days = days_in_range(date_from, date_to)
        if len(days) == 7 and date_from.weekday() == 0:
            return days
    start = date_from - timedelta(days=date_from.weekday())
    return days_in_range(start, start + timedelta(days=6))


def build_week_block(port, days: list[date], rows: list) -> MonthBlock:
    labels, pos_index, _counts = prepare_availability_layout(port, rows)
    by_day = bookings_by_day(rows)
    n_pos = max(len(labels), 1)
    count = sum(len(by_day.get(day, [])) for day in days)
    dates = [_day_stamp(day) for day in days]
    pos_rows: list[tuple[str, list[str]]] = []
    for index, label in enumerate(labels):
        cells: list[str] = []
        for day in days:
            ships = [
                booking
                for booking in by_day.get(day, [])
                if _slot_index(booking, pos_index, n_pos) == index
            ]
            cells.append(_ship_cell(ships) if ships else "0")
        pos_rows.append((label, cells))
    start, end = days[0], days[-1]
    return MonthBlock(
        year=start.year,
        month=start.month,
        title=week_title(start, end),
        total=len(rows),
        labels=labels,
        weeks=[WeekBand(count=count, dates=dates, rows=pos_rows)],
        weekday_labels=WEEKDAYS_WEEK_SHORT,
    )


def _slot_index(booking, pos_index: dict[int, int], n_pos: int) -> int:
    idx = pos_index.get(booking.position_id)
    if idx is None:
        return n_pos - 1
    return idx


def _ship_cell(bookings: list) -> str:
    names = []
    for booking in bookings:
        name = booking.vessel.name if booking.vessel_id else ""
        if name and name not in names:
            names.append(name)
    return " / ".join(names)


def _day_stamp(value: date) -> str:
    return f"{value.day}-{MONTHS_SHORT[value.month - 1]}-{value.year % 100:02d}"
