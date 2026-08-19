"""Availability chart JSON plus list export (ship / line / port / date / times / position)."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from io import BytesIO, StringIO
from typing import Any

from django.core.files.storage import default_storage
from django.db.models import Q
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from apps.bookings.services.report_exports.common import scheduled_bookings_qs
from apps.catalogs.models import Port, Position, PositionComponent
from apps.catalogs.utils.position_code import position_short_code
from apps.bookings.services.validation.conflict_display import (
    booking_conflict_display,
    cell_matches_conflict_filter,
)

# Occupancy density filter (Barcos por día) — exact distinct ships on that day.
SHIPS_PER_DAY_MIN = 1
SHIPS_PER_DAY_MAX = 4


def _related_column_indexes(
    positions: list[Position],
    position_index: dict[int, int],
) -> dict[int, list[int]]:
    """Map each position to chart columns it occupies (self + combined siblings)."""
    ids = [position.id for position in positions]
    related: dict[int, set[int]] = {pid: {pid} for pid in ids}
    links = PositionComponent.objects.filter(
        Q(combined_position_id__in=ids) | Q(source_position_id__in=ids)
    ).values_list("combined_position_id", "source_position_id")
    for combined_id, source_id in links:
        if combined_id in related and source_id in related:
            related[combined_id].add(source_id)
            related[source_id].add(combined_id)
    return {
        pid: sorted(
            position_index[rid] for rid in siblings if rid in position_index
        )
        for pid, siblings in related.items()
    }


def _day_ship_count(cells: list[list[dict]]) -> int:
    codes: set[str] = set()
    for cell in cells:
        for call in cell:
            code = call.get("booking_code")
            if code:
                codes.add(str(code))
    return len(codes)


EXPORT_HEADERS = [
    "Barco",
    "Naviera",
    "Puerto",
    "Fecha",
    "ETA",
    "ETD",
    "Posición",
]


def _format_export_time(value) -> str:
    if value is None:
        return ""
    return value.strftime("%H:%M")


def _port_display_name(port: Port) -> str:
    commercial = (port.commercial_name or "").strip()
    if commercial:
        return f"{port.name} ({commercial})"
    return port.name


def _position_display(booking) -> str:
    if not booking.position_id or booking.position is None:
        return ""
    return position_short_code(booking.port.code, booking.position.code)


def _availability_export_bookings(
    *,
    port_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
    shipping_line_id: int | None = None,
    vessel_id: int | None = None,
    position_id: int | None = None,
    status: str | None = None,
    statuses: list[str] | None = None,
):
    if allowed_ports is not None and port_id not in allowed_ports:
        raise ValueError("Puerto no permitido.")

    Port.objects.get(pk=port_id)
    status_filters = list(statuses or [])
    if status and status not in status_filters:
        status_filters.append(status)

    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        port_id=port_id,
        allowed_ports=allowed_ports,
        shipping_line_id=shipping_line_id,
        vessel_id=vessel_id,
        position_id=position_id,
        status=None,
    )
    if "c" in status_filters:
        from apps.bookings.models import Booking
        from apps.bookings.utils.status_query import apply_booking_status_filters

        base = Booking.objects.filter(
            call_date__gte=date_from,
            call_date__lte=date_to,
            port_id=port_id,
        ).select_related("port", "shipping_line", "vessel", "position")
        if allowed_ports is not None:
            base = base.filter(port_id__in=allowed_ports)
        if shipping_line_id:
            base = base.filter(shipping_line_id=shipping_line_id)
        if vessel_id:
            base = base.filter(vessel_id=vessel_id)
        if position_id:
            base = base.filter(position_id=position_id)
        qs = apply_booking_status_filters(base, status_filters)
    elif status_filters:
        from apps.bookings.utils.status_query import apply_booking_status_filters

        qs = apply_booking_status_filters(qs, status_filters)
    return qs.order_by("call_date", "position__sort_order", "vessel__name")


def _availability_export_rows(
    *,
    port_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
    shipping_line_id: int | None = None,
    vessel_id: int | None = None,
    position_id: int | None = None,
    status: str | None = None,
    statuses: list[str] | None = None,
) -> tuple[list[str], list[list[str]]]:
    qs = _availability_export_bookings(
        port_id=port_id,
        date_from=date_from,
        date_to=date_to,
        allowed_ports=allowed_ports,
        shipping_line_id=shipping_line_id,
        vessel_id=vessel_id,
        position_id=position_id,
        status=status,
        statuses=statuses,
    )
    rows: list[list[str]] = []
    for booking in qs.iterator(chunk_size=500):
        rows.append(
            [
                booking.vessel.name if booking.vessel_id else "",
                booking.shipping_line.name if booking.shipping_line_id else "",
                _port_display_name(booking.port),
                booking.call_date.strftime("%d/%m/%Y"),
                _format_export_time(booking.eta),
                _format_export_time(booking.etd),
                _position_display(booking),
            ]
        )
    return EXPORT_HEADERS, rows


def build_availability_data(
    *,
    port_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
    shipping_line_id: int | None = None,
    vessel_id: int | None = None,
    position_id: int | None = None,
    status: str | None = None,
    statuses: list[str] | None = None,
    has_conflict: bool | None = None,
    conflict_severity: str | None = None,
    conflict_type: str | None = None,
    ships_per_day: int | None = None,
    page: int | None = None,
    page_size: int = 30,
    request: Any = None,
) -> dict:
    """JSON payload for the on-screen Availability Chart (day × position)."""
    if allowed_ports is not None and port_id not in allowed_ports:
        raise ValueError("Puerto no permitido.")
    if ships_per_day is not None and (
        ships_per_day < SHIPS_PER_DAY_MIN or ships_per_day > SHIPS_PER_DAY_MAX
    ):
        raise ValueError(
            f"ships_per_day debe estar entre {SHIPS_PER_DAY_MIN} y {SHIPS_PER_DAY_MAX}."
        )
    if page is not None and page < 1:
        raise ValueError("page debe ser >= 1.")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size debe estar entre 1 y 100.")

    port = Port.objects.get(pk=port_id)
    from apps.catalogs.services.position_combination import exclude_combined_positions

    positions_qs = exclude_combined_positions(
        Position.objects.filter(port_id=port_id, is_active=True)
    )
    if position_id:
        positions_qs = positions_qs.filter(pk=position_id)
    positions = list(
        positions_qs.select_related("berth").order_by("sort_order", "code")
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

    status_filters = list(statuses or [])
    if status and status not in status_filters:
        status_filters.append(status)
    qs_kwargs = dict(
        date_from=date_from,
        date_to=date_to,
        port_id=port_id,
        allowed_ports=allowed_ports,
        shipping_line_id=shipping_line_id,
        vessel_id=vessel_id,
        position_id=position_id,
    )
    # Always load the occupancy set so neighbors stay visible with any status filter.
    bookings = list(scheduled_bookings_qs(**qs_kwargs, status=None))
    if "c" in status_filters:
        seen = {b.id for b in bookings}
        for booking in scheduled_bookings_qs(**qs_kwargs, status="c"):
            if booking.id not in seen:
                bookings.append(booking)
    if (
        has_conflict is not None
        or conflict_severity in {"yellow", "red", "green"}
        or conflict_type
    ):
        bookings = [
            b
            for b in bookings
            if cell_matches_conflict_filter(
                {
                    "has_conflict": bool(getattr(b, "has_conflict", False)),
                    "conflict_severity": getattr(b, "conflict_severity", None),
                    "conflict_snapshot": getattr(b, "conflict_snapshot", None),
                },
                has_conflict=has_conflict,
                conflict_severity=conflict_severity,
                conflict_type=conflict_type,
            )
        ]
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
    related_indexes = _related_column_indexes(positions, position_index)
    for booking in bookings:
        if booking.position_id in position_index:
            cell_indexes = related_indexes.get(
                booking.position_id,
                [position_index[booking.position_id]],
            )
        elif unassigned_index is not None:
            cell_indexes = [unassigned_index]
        else:
            continue
        day_cells = bookings_by_day.setdefault(
            booking.call_date,
            [[] for _ in range(cell_count)],
        )
        logo_name = booking.shipping_line.logo.name if booking.shipping_line.logo else None
        logo = default_storage.url(logo_name) if logo_name else None
        if logo and request is not None:
            logo = request.build_absolute_uri(logo)
        vessel_logo_name = booking.vessel.logo.name if booking.vessel.logo else None
        vessel_logo = (
            default_storage.url(vessel_logo_name) if vessel_logo_name else None
        )
        if vessel_logo and request is not None:
            vessel_logo = request.build_absolute_uri(vessel_logo)
        conflict_display = booking_conflict_display(
            has_conflict=bool(getattr(booking, "has_conflict", False)),
            conflict_severity=getattr(booking, "conflict_severity", None),
            snapshot=getattr(booking, "conflict_snapshot", None) or [],
        )
        call = {
            "booking_code": booking.booking_code,
            "status": booking.status,
            "conflict_chips": conflict_display["conflict_chips"],
            "conflict_highlights": conflict_display["conflict_highlights"],
            "position_id": booking.position_id or 0,
            "shipping_line_name": booking.shipping_line.name,
            "shipping_line_logo": logo,
            "vessel_name": booking.vessel.name,
            "vessel_logo": vessel_logo,
            "loa_m": (
                str(booking.vessel.loa_m)
                if booking.vessel.loa_m is not None
                else None
            ),
            "eta": booking.eta.isoformat() if booking.eta else None,
            "etd": booking.etd.isoformat() if booking.etd else None,
        }
        for cell_index in cell_indexes:
            existing = day_cells[cell_index]
            if any(item.get("booking_code") == call["booking_code"] for item in existing):
                continue
            existing.append(call)

    if ships_per_day is not None:
        matching_days = sorted(
            day
            for day, cells in bookings_by_day.items()
            if date_from <= day <= date_to and _day_ship_count(cells) == ships_per_day
        )
        matched_total = len(matching_days)
        use_page = page if page is not None else 1
        start = (use_page - 1) * page_size
        end = start + page_size
        page_days = matching_days[start:end]
        rows = [
            {
                "date": day.isoformat(),
                "cells": bookings_by_day.get(day, [[] for _ in range(cell_count)]),
            }
            for day in page_days
        ]
        return {
            "port_id": port.id,
            "port_code": port.code,
            "port_name": port.name,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "columns": columns,
            "rows": rows,
            "ships_per_day": ships_per_day,
            "matched_days": matched_total,
            "page": use_page,
            "page_size": page_size,
            "has_more": end < matched_total,
        }

    # Conflict filter: only days with calls after filtering (paginated).
    if (
        has_conflict is not None
        or conflict_severity in {"yellow", "red", "green"}
        or conflict_type
    ):
        matching_days = sorted(
            day
            for day, cells in bookings_by_day.items()
            if date_from <= day <= date_to and _day_ship_count(cells) >= 1
        )
        matched_total = len(matching_days)
        use_page = page if page is not None else 1
        start = (use_page - 1) * page_size
        end = start + page_size
        page_days = matching_days[start:end]
        rows = [
            {
                "date": day.isoformat(),
                "cells": bookings_by_day.get(day, [[] for _ in range(cell_count)]),
            }
            for day in page_days
        ]
        return {
            "port_id": port.id,
            "port_code": port.code,
            "port_name": port.name,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "columns": columns,
            "rows": rows,
            "matched_days": matched_total,
            "page": use_page,
            "page_size": page_size,
            "has_more": end < matched_total,
        }

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
    shipping_line_id: int | None = None,
    vessel_id: int | None = None,
    position_id: int | None = None,
    status: str | None = None,
    statuses: list[str] | None = None,
) -> bytes:
    header, rows = _availability_export_rows(
        port_id=port_id,
        date_from=date_from,
        date_to=date_to,
        allowed_ports=allowed_ports,
        shipping_line_id=shipping_line_id,
        vessel_id=vessel_id,
        position_id=position_id,
        status=status,
        statuses=statuses,
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "Disponibilidad"
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    for row in rows:
        ws.append(row)
    widths = (28, 28, 24, 12, 10, 10, 14)
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_availability_chart_csv(
    *,
    port_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
    shipping_line_id: int | None = None,
    vessel_id: int | None = None,
    position_id: int | None = None,
    status: str | None = None,
    statuses: list[str] | None = None,
) -> bytes:
    header, rows = _availability_export_rows(
        port_id=port_id,
        date_from=date_from,
        date_to=date_to,
        allowed_ports=allowed_ports,
        shipping_line_id=shipping_line_id,
        vessel_id=vessel_id,
        position_id=position_id,
        status=status,
        statuses=statuses,
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
