"""Shared month grouping for calendar flyers (PDF + Excel)."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, time

from apps.bookings.services.arrivals_pdf.labels import sunday_first_pad


def group_port_months(bookings: list):
    buckets: dict[tuple[int, int, int], list] = defaultdict(list)
    for booking in bookings:
        buckets[
            (booking.port_id, booking.call_date.year, booking.call_date.month)
        ].append(booking)

    def sort_key(item):
        sample = item[1][0]
        _port_id, year, month = item[0]
        return ((sample.port.name or "").lower(), year, month)

    out = []
    for key, rows in sorted(buckets.items(), key=sort_key):
        rows.sort(
            key=lambda b: (
                b.call_date,
                b.eta or time.min,
                (b.vessel.name if b.vessel_id else "").lower(),
            )
        )
        out.append((rows[0].port, key[1], key[2], rows))
    return out


def month_weeks(year: int, month: int) -> list[list[date | None]]:
    first = date(year, month, 1)
    pad = sunday_first_pad(first)
    days = monthrange(year, month)[1]
    cells: list[date | None] = [None] * pad
    for day in range(1, days + 1):
        cells.append(date(year, month, day))
    while len(cells) % 7:
        cells.append(None)
    return [cells[i : i + 7] for i in range(0, len(cells), 7)]


def bookings_by_day(rows: list) -> dict[date, list]:
    grouped: dict[date, list] = defaultdict(list)
    for booking in rows:
        grouped[booking.call_date].append(booking)
    for day_rows in grouped.values():
        day_rows.sort(
            key=lambda b: (
                b.eta or time.min,
                (b.vessel.name if b.vessel_id else "").lower(),
            )
        )
    return grouped


def months_in_range(date_from: date, date_to: date) -> list[tuple[int, int]]:
    """Inclusive year-month pairs covering date_from .. date_to."""
    months: list[tuple[int, int]] = []
    year, month = date_from.year, date_from.month
    last = (date_to.year, date_to.month)
    while (year, month) <= last:
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def excel_sheet_title(raw: str) -> str:
    cleaned = "".join(ch for ch in raw if ch not in r"[]:*?/\\")
    cleaned = cleaned.strip() or "Hoja"
    return cleaned[:31]
