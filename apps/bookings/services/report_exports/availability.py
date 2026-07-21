"""Availability Chart export — day × position matrix (carrier + LOA)."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO, StringIO
from typing import Any

from django.core.files.storage import default_storage
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from apps.bookings.services.report_exports.common import scheduled_bookings_qs
from apps.catalogs.models import Port, Position


def _availability_matrix(
    *,
    port_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
) -> tuple[list[str], list[list[str]]]:
    if allowed_ports is not None and port_id not in allowed_ports:
        raise ValueError("Puerto no permitido.")

    Port.objects.get(pk=port_id)
    positions = list(
        Position.objects.filter(port_id=port_id, is_active=True)
        .select_related("berth")
        .order_by("sort_order", "code")
    )
    pos_codes = [p.code for p in positions]
    pos_by_id = {p.id: p.code for p in positions}

    cells: dict[tuple[date, str], list[str]] = defaultdict(list)
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        port_id=port_id,
        allowed_ports=allowed_ports,
    )
    for b in qs.iterator(chunk_size=500):
        code = pos_by_id.get(b.position_id) if b.position_id else "TBD"
        line = (b.shipping_line.code or b.shipping_line.name or "").strip() or "?"
        loa = ""
        if b.vessel_id and b.vessel.loa_m is not None:
            loa_val = b.vessel.loa_m
            loa = str(int(loa_val) if loa_val == int(loa_val) else loa_val)
        cells[(b.call_date, code)].append(f"{line} {loa}".strip() if loa else line)

    if "TBD" not in pos_codes and any(k[1] == "TBD" for k in cells):
        pos_codes = [*pos_codes, "TBD"]

    header = ["Fecha", *pos_codes]
    rows: list[list[str]] = []
    day = date_from
    while day <= date_to:
        row = [day.isoformat()]
        for code in pos_codes:
            vals = cells.get((day, code), [])
            row.append(" | ".join(vals) if vals else "0")
        rows.append(row)
        day += timedelta(days=1)
    return header, rows


def build_availability_data(
    *,
    port_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
    request: Any = None,
) -> dict:
    """JSON payload for the on-screen Availability Chart (day × position)."""
    if allowed_ports is not None and port_id not in allowed_ports:
        raise ValueError("Puerto no permitido.")
    port = Port.objects.get(pk=port_id)
    positions = list(
        Position.objects.filter(port_id=port_id, is_active=True)
        .select_related("berth")
        .order_by("sort_order", "code")
    )
    position_index = {position.id: index for index, position in enumerate(positions)}
    columns = [
        {
            "id": position.id,
            "code": position.code,
            "label": (
                position.code.removeprefix(f"{port.code}-")
                if position.code.startswith(f"{port.code}-")
                else position.code
            ),
            "berth_name": position.berth.name if position.berth_id else "",
            "max_loa_m": (
                str(position.max_loa_m) if position.max_loa_m is not None else None
            ),
        }
        for position in positions
    ]
    bookings = list(
        scheduled_bookings_qs(
            date_from=date_from,
            date_to=date_to,
            port_id=port_id,
            allowed_ports=allowed_ports,
        )
    )
    has_unassigned = any(booking.position_id not in position_index for booking in bookings)
    unassigned_index = len(positions) if has_unassigned else None
    if has_unassigned:
        columns.append(
            {
                "id": 0,
                "code": "TBD",
                "label": "TBD",
                "berth_name": "Sin asignar",
                "max_loa_m": None,
            }
        )

    bookings_by_day: dict[date, list[list[dict]]] = {}
    cell_count = len(columns)
    for booking in bookings:
        cell_index = position_index.get(booking.position_id, unassigned_index)
        if cell_index is None:
            continue
        day_cells = bookings_by_day.setdefault(
            booking.call_date,
            [[] for _ in range(cell_count)],
        )
        logo_name = booking.shipping_line.logo.name if booking.shipping_line.logo else None
        logo = default_storage.url(logo_name) if logo_name else None
        if logo and request is not None:
            logo = request.build_absolute_uri(logo)
        day_cells[cell_index].append(
            {
                "booking_code": booking.booking_code,
                "shipping_line_name": booking.shipping_line.name,
                "shipping_line_logo": logo,
                "vessel_name": booking.vessel.name,
                "loa_m": (
                    str(booking.vessel.loa_m)
                    if booking.vessel.loa_m is not None
                    else None
                ),
            }
        )

    rows = []
    day = date_from
    while day <= date_to:
        rows.append(
            {
                "date": day.isoformat(),
                "cells": bookings_by_day.get(day, [[] for _ in range(cell_count)]),
            }
        )
        day += timedelta(days=1)

    return {
        "port_id": port.id,
        "port_code": port.code,
        "port_name": port.name,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "columns": columns,
        "rows": rows,
    }


def build_availability_chart_xlsx(
    *,
    port_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
) -> bytes:
    header, rows = _availability_matrix(
        port_id=port_id,
        date_from=date_from,
        date_to=date_to,
        allowed_ports=allowed_ports,
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "Availability"
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    for row in rows:
        ws.append(row)
    ws.column_dimensions["A"].width = 12
    for idx in range(2, len(header) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 16
    ws.freeze_panes = "B2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_availability_chart_csv(
    *,
    port_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
) -> bytes:
    header, rows = _availability_matrix(
        port_id=port_id,
        date_from=date_from,
        date_to=date_to,
        allowed_ports=allowed_ports,
    )
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def availability_filename(
    port_code: str,
    date_from: date,
    date_to: date,
    ext: str = "xlsx",
) -> str:
    return f"availability_{port_code}_{date_from.isoformat()}_{date_to.isoformat()}.{ext}"
