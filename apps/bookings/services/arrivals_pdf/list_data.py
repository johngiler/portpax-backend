"""Shared CALL LIST rows for list PDF (vertical) and list Excel (horizontal)."""

from __future__ import annotations

from collections import defaultdict
from datetime import time

from apps.bookings.services.arrivals_pdf.labels import format_hhmm, list_date_label
from apps.bookings.services.arrivals_pdf.occupancy import brand_short, loa_label
from apps.bookings.services.validation.legend_labels import position_legend_label

LIST_HEADERS = (
    "N/M",
    "Fecha",
    "Crucero",
    "Naviera",
    "Grupo",
    "Marca",
    "LOA",
    "Cap.",
    "Estado",
    "ETA",
    "ETD",
    "Posición",
)
LIST_CENTER_COLS = {0, 4, 5, 6, 7, 8, 9, 10, 11}


def group_bookings_by_port(bookings: list) -> list[tuple]:
    buckets: dict[int, list] = defaultdict(list)
    for booking in bookings:
        buckets[booking.port_id].append(booking)
    ordered = []
    for _port_id, rows in buckets.items():
        rows.sort(
            key=lambda b: (
                b.call_date,
                b.eta or time.min,
                (b.vessel.name if b.vessel_id else "").lower(),
            )
        )
        ordered.append((rows[0].port, rows))
    ordered.sort(key=lambda item: (item[0].name or "").lower())
    return ordered


def list_row_values(booking, *, number: int) -> tuple[str, ...]:
    line = booking.shipping_line if booking.shipping_line_id else None
    group = getattr(line, "group", None) if line is not None else None
    vessel = booking.vessel if booking.vessel_id else None
    position = ""
    if booking.position_id:
        label = position_legend_label(booking.position)
        position = "" if label == "?" else label
    cap = ""
    if vessel is not None and vessel.pax_capacity is not None:
        cap = f"{int(vessel.pax_capacity):,}".replace(",", ".")
    return (
        str(number),
        list_date_label(booking.call_date),
        vessel.name if vessel is not None else "",
        line.name if line is not None else "",
        brand_short(group),
        brand_short(line),
        loa_label(vessel),
        cap,
        (booking.status or "").upper(),
        format_hhmm(booking.eta),
        format_hhmm(booking.etd),
        position,
    )
