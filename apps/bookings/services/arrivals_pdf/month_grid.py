"""Shared month grouping for calendar flyers (PDF + Excel)."""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, time

from apps.bookings.services.arrivals_pdf.labels import sunday_first_pad


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


def parse_calendar_months(raw: str | None) -> list[int]:
    """1-based months 1–12, unique and sorted."""
    if not raw:
        return []
    seen: set[int] = set()
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            month = int(part)
        except ValueError:
            continue
        if month < 1 or month > 12 or month in seen:
            continue
        seen.add(month)
        out.append(month)
    out.sort()
    return out


def month_pairs(
    date_from: date | None,
    date_to: date | None,
    months: list[int] | None = None,
) -> list[tuple[int, int]]:
    """Year-month pairs in range, optionally filtered to 1-based `months`."""
    if date_from is None or date_to is None:
        return []
    pairs = months_in_range(date_from, date_to)
    if months:
        allowed = set(months)
        pairs = [(year, month) for year, month in pairs if month in allowed]
    return pairs


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


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def iter_port_months(
    bookings: list,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    ports: list | None = None,
    months: list[int] | None = None,
):
    """Every port × every month in range (empty months included)."""
    from apps.bookings.services.arrivals_pdf.list_data import group_bookings_by_port

    grouped = group_bookings_by_port(bookings)
    by_port = {port.id: rows for port, rows in grouped}
    port_list = list(ports or [port for port, _rows in grouped])
    if date_from is not None and date_to is not None:
        pairs = months_in_range(date_from, date_to)
    else:
        pairs = sorted(
            {
                (booking.call_date.year, booking.call_date.month)
                for booking in bookings
                if getattr(booking, "call_date", None)
            }
        )
    if months:
        allowed = set(months)
        pairs = [(year, month) for year, month in pairs if month in allowed]
    out = []
    for port in port_list:
        rows = by_port.get(port.id, [])
        for year, month in pairs:
            month_rows = [
                booking
                for booking in rows
                if booking.call_date.year == year and booking.call_date.month == month
            ]
            out.append((port, year, month, month_rows))
    return out


def excel_sheet_title(raw: str) -> str:
    cleaned = "".join(ch for ch in raw if ch not in r"[]:*?/\\")
    cleaned = cleaned.strip() or "Hoja"
    return cleaned[:31]
