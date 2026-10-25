"""Occupancy cell copy for availability flyers (Beto chart as reference)."""

from __future__ import annotations

from datetime import date, timedelta

from apps.bookings.services.arrivals_pdf.labels import MONTHS_SHORT, WEEKDAYS_SHORT


def occupancy_date_label(value: date) -> str:
    return (
        f"{value.day:02d}/{MONTHS_SHORT[value.month - 1]}/"
        f"{value.year % 100:02d}"
    )


def occupancy_weekday(value: date) -> str:
    return WEEKDAYS_SHORT[value.weekday()]


_BRAND_SKIP = {
    "de",
    "del",
    "la",
    "el",
    "the",
    "of",
    "and",
    "y",
}


def brand_short(line) -> str:
    """Compact brand like Beto's RCCL / NCL / MSC."""
    if line is None:
        return ""
    name = (getattr(line, "name", None) or "").strip()
    words = [
        part
        for part in name.replace("-", " ").split()
        if part and part.lower() not in _BRAND_SKIP
    ]
    if words:
        first = words[0]
        if first.isupper() and 2 <= len(first) <= 6:
            return first
        initials = "".join(word[0] for word in words if word[:1].isalpha())
        if len(initials) >= 2:
            return initials.upper()[:6]
    code = (getattr(line, "code", None) or "").strip()
    if code:
        return code.replace("-", " ").replace("_", " ").split()[0].upper()[:6]
    return name[:6].upper() if name else ""


def loa_label(vessel) -> str:
    if vessel is None or getattr(vessel, "loa_m", None) is None:
        return ""
    value = vessel.loa_m
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def occupancy_cell_lines(booking) -> list[str]:
    """Brand + LOA (Beto) and vessel name (PortPax)."""
    brand = brand_short(getattr(booking, "shipping_line", None))
    loa = loa_label(getattr(booking, "vessel", None) if booking.vessel_id else None)
    head = " ".join(part for part in (brand, loa) if part)
    vessel = booking.vessel.name if booking.vessel_id else ""
    lines = [part for part in (head, vessel) if part]
    return lines or ["—"]


def occupancy_cell_text(booking) -> str:
    return "\n".join(occupancy_cell_lines(booking))


def days_in_range(date_from: date, date_to: date) -> list[date]:
    days: list[date] = []
    cursor = date_from
    while cursor <= date_to:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def prepare_availability_layout(port, bookings: list):
    labels, pos_index = load_availability_positions(port)
    has_unassigned = any(
        getattr(booking, "position_id", None) not in pos_index for booking in bookings
    )
    if not labels:
        labels = ["—"]
    elif has_unassigned:
        labels = [*labels, "—"]
    counts = position_call_counts(bookings, pos_index, len(labels))
    return labels, pos_index, counts


def load_availability_positions(port) -> tuple[list[str], dict[int, int]]:
    from apps.catalogs.models import Position
    from apps.catalogs.services.position_combination import exclude_combined_positions
    from apps.catalogs.utils.position_code import position_short_code

    positions = list(
        exclude_combined_positions(
            Position.objects.filter(port_id=port.id, is_active=True)
        )
        .select_related("berth")
        .order_by("sort_order", "code")
    )
    labels = [
        position_short_code(port.code, position.code) for position in positions
    ]
    pos_index = {position.id: i for i, position in enumerate(positions)}
    return labels, pos_index


def position_call_counts(
    bookings: list, pos_index: dict[int, int], n_pos: int
) -> list[int]:
    counts = [0] * max(n_pos, 1)
    for booking in bookings:
        idx = pos_index.get(booking.position_id)
        if idx is None:
            counts[-1] += 1
        else:
            counts[idx] += 1
    return counts
