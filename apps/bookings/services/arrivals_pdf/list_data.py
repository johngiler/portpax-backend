"""Shared CALL LIST rows for list PDF (vertical) and list Excel (horizontal)."""

from __future__ import annotations

from collections import defaultdict
from datetime import time

from apps.bookings.models import BookingStatus
from apps.bookings.services.arrivals_pdf.labels import format_hhmm, list_date_label
from apps.bookings.services.arrivals_pdf.occupancy import brand_short, loa_label
from apps.bookings.services.report_exports.common import (
    PAX_BASIS_PLANNED,
    booking_pax,
    format_pax_count,
)
from apps.bookings.services.validation.legend_labels import position_legend_label
from apps.bookings.utils.status_query import parse_status_query_params

LIST_HEADERS = (
    "N/M",
    "Fecha",
    "Crucero",
    "Naviera",
    "Grupo",
    "Marca",
    "LOA",
    "Cap.",
    "PAX",
    "Estado",
    "ETA",
    "ETD",
    "Posición",
)
CANCEL_HEADERS = ("Motivo", "Observaciones")
LIST_CENTER_COLS = {0, 4, 5, 6, 7, 8, 9, 10, 11, 12}

COL_FRACS = (
    0.035,
    0.12,
    0.155,
    0.135,
    0.055,
    0.055,
    0.05,
    0.055,
    0.055,
    0.055,
    0.05,
    0.05,
    0.13,
)
CANCEL_COL_FRACS = (
    0.03,
    0.10,
    0.12,
    0.10,
    0.045,
    0.045,
    0.04,
    0.05,
    0.05,
    0.05,
    0.04,
    0.04,
    0.07,
    0.09,
    0.13,
)
COL_WIDTHS = (5, 14, 16, 18, 9, 9, 8, 9, 9, 8, 8, 8, 10)
CANCEL_COL_WIDTHS = (5, 13, 15, 16, 8, 8, 7, 8, 8, 8, 7, 7, 9, 14, 22)


def include_list_cancellation(query) -> bool:
    """Motivo / observaciones only when the list is filtered to cancelled."""
    if query is None:
        return False
    return BookingStatus.C in parse_status_query_params(query)


def list_headers(*, include_cancellation: bool = False) -> tuple[str, ...]:
    if include_cancellation:
        return LIST_HEADERS + CANCEL_HEADERS
    return LIST_HEADERS


def list_center_cols(*, include_cancellation: bool = False) -> set[int]:
    return LIST_CENTER_COLS


def list_col_fracs(*, include_cancellation: bool = False) -> tuple[float, ...]:
    return CANCEL_COL_FRACS if include_cancellation else COL_FRACS


def list_col_widths(*, include_cancellation: bool = False) -> tuple[float, ...]:
    return CANCEL_COL_WIDTHS if include_cancellation else COL_WIDTHS


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


def list_row_values(
    booking,
    *,
    number: int,
    pax_basis: str = PAX_BASIS_PLANNED,
    include_cancellation: bool = False,
) -> tuple[str, ...]:
    line = booking.shipping_line if booking.shipping_line_id else None
    group = getattr(line, "group", None) if line is not None else None
    vessel = booking.vessel if booking.vessel_id else None
    position = ""
    if booking.position_id:
        label = position_legend_label(booking.position)
        position = "" if label == "?" else label
    cap = ""
    if vessel is not None and vessel.pax_capacity is not None:
        cap = format_pax_count(int(vessel.pax_capacity))
    pax = format_pax_count(booking_pax(booking, pax_basis=pax_basis))
    values = (
        str(number),
        list_date_label(booking.call_date),
        vessel.name if vessel is not None else "",
        line.name if line is not None else "",
        brand_short(group),
        brand_short(line),
        loa_label(vessel),
        cap,
        pax,
        (booking.status or "").upper(),
        format_hhmm(booking.eta),
        format_hhmm(booking.etd),
        position,
    )
    if not include_cancellation:
        return values
    reason = ""
    notes = ""
    if booking.status == BookingStatus.C:
        if booking.cancellation_reason:
            reason = booking.get_cancellation_reason_display()
        notes = booking.cancellation_notes or ""
    return values + (reason, notes)
