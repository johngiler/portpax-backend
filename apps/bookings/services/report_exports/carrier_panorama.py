"""Panorama Navieras — calls / PAX by port × year plus participation KPIs."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from io import BytesIO, StringIO
from typing import Any

import csv
from openpyxl import Workbook

from apps.bookings.services.report_exports.common import (
    booking_pax,
    normalize_pax_basis,
    pax_basis_note,
    scheduled_bookings_qs,
    years_in_range,
)
from apps.bookings.services.report_exports.filenames import report_download_filename
from apps.bookings.services.report_exports.xlsx_style import (
    ALIGN_LEFT,
    ALIGN_RIGHT,
    BORDER_ALL,
    FILL_ALT,
    FILL_ROW_LABEL,
    FILL_TOTAL,
    FONT_DATA,
    FONT_ROW_LABEL,
    FONT_TOTAL,
    autosize_columns,
    prepare_report_sheet,
    strip_block_outer_border,
    style_cell,
    write_column_header_band,
    write_report_banner,
    write_section_banner,
)
from apps.bookings.services.report_exports.matrix_reports import _logo_assets
from apps.bookings.services.validation.legend_labels import port_legend_label
from apps.catalogs.models import Port, ShippingLine, ShippingLineGroup


def _port_friendly_name(port: Port | None) -> str:
    label = port_legend_label(port).strip()
    if label:
        return label
    if port is None:
        return "Puerto"
    return (getattr(port, "name", None) or getattr(port, "code", None) or "Puerto").strip()


def _excel_sheet_title(label: str) -> str:
    cleaned = (label or "Hoja").strip()
    for ch in r"\/*?:[]":
        cleaned = cleaned.replace(ch, "-")
    return (cleaned.strip() or "Hoja")[:31]


def _subject_name(
    *,
    shipping_line_id: int | None,
    shipping_line_group_id: int | None,
) -> str:
    if shipping_line_id:
        line = (
            ShippingLine.objects.filter(pk=shipping_line_id)
            .only("id", "name", "code")
            .first()
        )
        if line:
            return (line.name or line.code or "Naviera").strip()
    if shipping_line_group_id:
        group = (
            ShippingLineGroup.objects.filter(pk=shipping_line_group_id)
            .only("id", "name")
            .first()
        )
        if group:
            return (group.name or "Grupo").strip()
    return "navieras"


def _year_span_label(years: list[int]) -> str:
    if not years:
        return ""
    if years[0] == years[-1]:
        return str(years[0])
    return f"{years[0]}–{years[-1]}"


def _share_pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 1000) / 10


def build_carrier_panorama(
    *,
    date_from: date,
    date_to: date,
    shipping_line_id: int | None = None,
    shipping_line_group_id: int | None = None,
    without_lta: bool = False,
    pax_basis: str = "planned",
    port_ids: set[int] | list[int] | None = None,
    allowed_ports: set[int] | list[int] | None = None,
    request=None,
) -> dict[str, Any]:
    basis = normalize_pax_basis(pax_basis)
    years = years_in_range(date_from, date_to)
    subject = _subject_name(
        shipping_line_id=shipping_line_id,
        shipping_line_group_id=shipping_line_group_id,
    )

    scoped: set[int] | None = (
        set(allowed_ports) if allowed_ports is not None else None
    )
    wanted = {int(pid) for pid in (port_ids or []) if pid}
    if wanted:
        scoped = wanted if scoped is None else scoped & wanted

    ports_qs = Port.objects.filter(is_active=True).only(
        "id", "name", "code", "commercial_name", "logo"
    )
    if scoped is not None:
        ports_qs = ports_qs.filter(id__in=scoped)
    ports = list(ports_qs.order_by("name"))

    cells: dict[int, dict[int, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"calls": 0, "pax": 0})
    )
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        shipping_line_id=shipping_line_id,
        shipping_line_group_id=shipping_line_group_id,
        allowed_ports=scoped,
        without_lta=without_lta,
    )
    for booking in qs.iterator(chunk_size=500):
        year = booking.call_date.year
        if year not in years:
            continue
        cell = cells[booking.port_id][year]
        cell["calls"] += 1
        cell["pax"] += booking_pax(booking, pax_basis=basis)

    rows: list[dict[str, Any]] = []
    totals_by_year = {year: {"calls": 0, "pax": 0} for year in years}
    grand_calls = 0
    grand_pax = 0
    ports_with_calls = 0

    for port in ports:
        by_year: list[dict[str, int]] = []
        row_calls = 0
        row_pax = 0
        for year in years:
            cell = cells[port.id][year]
            calls = int(cell["calls"])
            pax = int(cell["pax"])
            by_year.append({"year": year, "calls": calls, "pax": pax})
            totals_by_year[year]["calls"] += calls
            totals_by_year[year]["pax"] += pax
            row_calls += calls
            row_pax += pax
        if row_calls:
            ports_with_calls += 1
        grand_calls += row_calls
        grand_pax += row_pax
        assets = _logo_assets(port.logo, request)
        rows.append(
            {
                "port_id": port.id,
                "port_name": _port_friendly_name(port),
                "logo": assets["url"],
                "logo_name": assets["name"],
                "logo_path": assets["path"],
                "by_year": by_year,
                "total_calls": row_calls,
                "total_pax": row_pax,
            }
        )

    share_basis = grand_pax if grand_pax > 0 else grand_calls
    port_share = []
    for row in rows:
        weight = row["total_pax"] if grand_pax > 0 else row["total_calls"]
        if weight <= 0:
            continue
        port_share.append(
            {
                "port_id": row["port_id"],
                "port_name": row["port_name"],
                "calls": row["total_calls"],
                "pax": row["total_pax"],
                "share_pct": _share_pct(weight, share_basis),
            }
        )
    port_share.sort(key=lambda item: item["pax"] or item["calls"], reverse=True)

    year_label = _year_span_label(years)
    subtitle_bits = [year_label] if year_label else []
    subtitle_bits.append(
        "Cap. máx." if basis != "planned" else "Planificado"
    )
    if without_lta:
        subtitle_bits.append("Sin LTA")
    subtitle = " · ".join(bit for bit in subtitle_bits if bit)

    note = pax_basis_note(basis)
    if without_lta:
        note = f"{note} Excluye LTA."

    matrix_title = (
        f"Arribos y pasajeros totales programados por puerto ({year_label})"
        if year_label
        else "Arribos y pasajeros totales programados por puerto"
    )

    return {
        "kind": "carrier_panorama",
        "title": f"Panorama de {subject} en puertos ITM",
        "matrix_title": matrix_title,
        "subtitle": subtitle,
        "subject_name": subject,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "without_lta": without_lta,
        "pax_basis": basis,
        "years": years,
        "kpis": {
            "total_calls": grand_calls,
            "total_pax": grand_pax,
            "ports_with_calls": ports_with_calls,
            "ports_total": len(ports),
        },
        "port_share": port_share,
        "rows": rows,
        "totals": {
            "by_year": [
                {
                    "year": year,
                    "calls": totals_by_year[year]["calls"],
                    "pax": totals_by_year[year]["pax"],
                }
                for year in years
            ],
            "total_calls": grand_calls,
            "total_pax": grand_pax,
        },
        "note": note,
    }


def carrier_panorama_filename(ext: str = "xlsx") -> str:
    return report_download_filename("carrier_panorama", ext)


def _csv_bytes(rows: list[list[Any]]) -> bytes:
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _matrix_headers(years: list[int]) -> list[str]:
    headers = ["Puerto"]
    for year in years:
        headers.extend([f"{year} arribos", f"{year} PAX"])
    headers.extend(["Total arribos", "Total PAX"])
    return headers


def _matrix_values(item: dict[str, Any], years: list[int]) -> list[Any]:
    by_year = {cell["year"]: cell for cell in item.get("by_year") or []}
    values: list[Any] = []
    for year in years:
        cell = by_year.get(year) or {}
        values.extend([cell.get("calls") or 0, cell.get("pax") or 0])
    values.extend([item.get("total_calls") or 0, item.get("total_pax") or 0])
    return values


def build_carrier_panorama_csv(payload: dict[str, Any]) -> bytes:
    years = list(payload.get("years") or [])
    kpis = payload.get("kpis") or {}
    rows: list[list[Any]] = [
        [payload.get("title") or "Panorama Navieras"],
    ]
    subtitle = str(payload.get("subtitle") or "").strip()
    if subtitle:
        rows.append([subtitle])
    rows.append([])
    rows.append(["Indicador", "Valor"])
    rows.append(["Arribos totales", kpis.get("total_calls") or 0])
    rows.append(["PAX totales", kpis.get("total_pax") or 0])
    rows.append(
        [
            "Puertos con programación",
            f"{kpis.get('ports_with_calls') or 0} de {kpis.get('ports_total') or 0}",
        ]
    )
    rows.append([])
    rows.append(["Participación por puerto"])
    rows.append(["Puerto", "Arribos", "PAX", "%"])
    for item in payload.get("port_share") or []:
        rows.append(
            [
                item.get("port_name"),
                item.get("calls") or 0,
                item.get("pax") or 0,
                f"{item.get('share_pct') or 0}%",
            ]
        )
    rows.append([])
    rows.append(
        [payload.get("matrix_title") or "Arribos y pasajeros totales programados por puerto"]
    )
    rows.append(_matrix_headers(years))
    for item in payload.get("rows") or []:
        rows.append([item.get("port_name"), *_matrix_values(item, years)])
    totals = payload.get("totals") or {}
    rows.append(["TOTAL", *_matrix_values(totals, years)])
    return _csv_bytes(rows)


def _write_numeric_rows(
    ws,
    start_row: int,
    rows: list[list[Any]],
    *,
    col_count: int,
    emphasize_last: bool = False,
) -> int:
    row = start_row
    last = start_row + len(rows) - 1 if rows else start_row
    for idx, values in enumerate(rows):
        is_total = emphasize_last and row == last
        fill = FILL_TOTAL if is_total else (FILL_ALT if idx % 2 else None)
        font = FONT_TOTAL if is_total else FONT_DATA
        for col in range(1, col_count + 1):
            value = values[col - 1] if col - 1 < len(values) else ""
            cell = ws.cell(row=row, column=col, value=value)
            is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
            style_cell(
                cell,
                font=FONT_TOTAL if is_total and col == 1 else (
                    FONT_ROW_LABEL if col == 1 and not is_total else font
                ),
                fill=FILL_TOTAL if is_total else (
                    FILL_ROW_LABEL if col == 1 and not is_total else fill
                ),
                alignment=ALIGN_LEFT if col == 1 else ALIGN_RIGHT,
                border=BORDER_ALL,
                number_format="#,##0" if is_number else None,
            )
        row += 1
    return row


def build_carrier_panorama_xlsx(payload: dict[str, Any]) -> bytes:
    years = list(payload.get("years") or [])
    kpis = payload.get("kpis") or {}
    matrix_headers = _matrix_headers(years)
    col_span = max(len(matrix_headers), 4)

    wb = Workbook()
    ws = wb.active
    ws.title = _excel_sheet_title(payload.get("subject_name") or "Panorama")
    prepare_report_sheet(ws)

    row = write_report_banner(
        ws,
        1,
        title=str(payload.get("title") or "Panorama Navieras"),
        subtitle=str(payload.get("subtitle") or "").strip() or None,
        col_span=col_span,
    )

    write_section_banner(ws, row, "Indicadores", col_span)
    row += 1
    write_column_header_band(ws, row, ["Indicador", "Valor"])
    row += 1
    kpi_start = row
    row = _write_numeric_rows(
        ws,
        row,
        [
            ["Arribos totales", kpis.get("total_calls") or 0],
            ["PAX totales", kpis.get("total_pax") or 0],
            [
                "Puertos con programación",
                f"{kpis.get('ports_with_calls') or 0} de {kpis.get('ports_total') or 0}",
            ],
        ],
        col_count=2,
    )
    strip_block_outer_border(ws, min_row=kpi_start - 1, max_row=row - 1, min_col=1, max_col=2)
    row += 1

    write_section_banner(ws, row, "Participación por puerto", col_span)
    row += 1
    write_column_header_band(ws, row, ["Puerto", "Arribos", "PAX", "%"])
    row += 1
    share_start = row
    share_rows = [
        [
            item.get("port_name"),
            item.get("calls") or 0,
            item.get("pax") or 0,
            f"{item.get('share_pct') or 0}%",
        ]
        for item in payload.get("port_share") or []
    ]
    row = _write_numeric_rows(ws, row, share_rows, col_count=4)
    if row > share_start:
        strip_block_outer_border(
            ws, min_row=share_start - 1, max_row=row - 1, min_col=1, max_col=4
        )
    row += 1

    write_section_banner(
        ws,
        row,
        str(
            payload.get("matrix_title")
            or "Arribos y pasajeros totales programados por puerto"
        ),
        col_span,
    )
    row += 1
    write_column_header_band(ws, row, matrix_headers)
    row += 1
    body_start = row
    body_rows = [
        [item.get("port_name"), *_matrix_values(item, years)]
        for item in payload.get("rows") or []
    ]
    totals = payload.get("totals") or {}
    body_rows.append(["TOTAL", *_matrix_values(totals, years)])
    row = _write_numeric_rows(
        ws, row, body_rows, col_count=len(matrix_headers), emphasize_last=True
    )
    if row > body_start:
        strip_block_outer_border(
            ws,
            min_row=body_start - 1,
            max_row=row - 1,
            min_col=1,
            max_col=len(matrix_headers),
        )

    autosize_columns(ws, min_width=10, max_width=22)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
