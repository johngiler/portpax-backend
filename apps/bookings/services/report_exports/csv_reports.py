"""CSV builders for structured ReportsView exports."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from apps.bookings.services.report_exports.booking_movements import (
    MONTH_LABELS_ES,
    build_booking_movements_report,
)
from apps.bookings.services.report_exports.matrix_reports import (
    MONTH_LABELS,
    build_port_carrier_matrix,
    build_port_trends,
    build_ports_totals_matrix,
)


def _csv_bytes(rows: list[list[Any]]) -> bytes:
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _matrix_section_rows(
    *,
    title: str,
    sections: list[dict[str, Any]],
    metric_key: str,
) -> list[list[Any]]:
    out: list[list[Any]] = [[title], []]
    header = ["AÑO", *MONTH_LABELS, "TOTAL"]
    for section in sections:
        out.append([section.get("label") or ""])
        out.append(header)
        for data_row in section.get(metric_key) or []:
            label = (
                "TOTAL"
                if data_row.get("year") == "total"
                else str(data_row.get("year") or "")
            )
            out.append(
                [label, *(data_row.get("months") or []), data_row.get("total") or 0]
            )
        out.append([])
    return out


def build_ports_totals_matrix_csv(**kwargs) -> bytes:
    report = build_ports_totals_matrix(**kwargs)
    rows: list[list[Any]] = []
    rows.extend(
        _matrix_section_rows(
            title="CALL SUMMARY ITM PORTS",
            sections=report["sections"],
            metric_key="calls",
        )
    )
    rows.extend(
        _matrix_section_rows(
            title="PASSENGER SUMMARY ITM PORTS",
            sections=report["sections"],
            metric_key="pax",
        )
    )
    return _csv_bytes(rows)


def build_port_carrier_matrix_csv(**kwargs) -> bytes:
    report = build_port_carrier_matrix(**kwargs)
    port_name = report["port"]["name"]
    rows: list[list[Any]] = []
    rows.extend(
        _matrix_section_rows(
            title=f"CALL SUMMARY {port_name.upper()}",
            sections=report["sections"],
            metric_key="calls",
        )
    )
    rows.extend(
        _matrix_section_rows(
            title=f"PASSENGER SUMMARY {port_name.upper()}",
            sections=report["sections"],
            metric_key="pax",
        )
    )
    return _csv_bytes(rows)


def build_port_trends_csv(**kwargs) -> bytes:
    report = build_port_trends(**kwargs)
    years = report["years"]
    rows: list[list[Any]] = [
        [f"TRENDS — {report['port']['name'].upper()}"],
        [],
    ]
    header = ["Grupo / Naviera"]
    for year in years:
        header.extend([f"{year} SHIPS", f"{year} PAX"])
    header.extend(["Total SHIPS", "Total PAX"])
    rows.append(header)

    def append_metric(label: str, item: dict[str, Any]) -> None:
        values: list[Any] = [label]
        for cell in item.get("by_year") or []:
            values.extend([cell.get("ships") or "", cell.get("pax") or ""])
        values.extend([item.get("total_ships") or "", item.get("total_pax") or ""])
        rows.append(values)

    for group in report.get("groups") or []:
        append_metric(group["name"], group)
        for line in group.get("lines") or []:
            append_metric(f"  {line['name']}", line)
    totals = report.get("totals")
    if totals:
        append_metric("TOTAL", totals)

    rows.extend([[], ["GROWTH PERCENTAGE (PAX YoY)"], []])
    rows.append(["Grupo / Naviera", *[str(y) for y in years]])

    def append_growth(label: str, item: dict[str, Any]) -> None:
        pcts = []
        for g in item.get("growth") or []:
            pct = g.get("pct")
            pcts.append("" if pct is None else f"{pct}%")
        rows.append([label, *pcts])

    for group in report.get("groups") or []:
        append_growth(group["name"], group)
        for line in group.get("lines") or []:
            append_growth(f"  {line['name']}", line)
    if totals:
        append_growth("TOTAL", totals)

    return _csv_bytes(rows)


def build_booking_movements_csv(*, year: int, allowed_ports=None) -> bytes:
    payload = build_booking_movements_report(year=year, allowed_ports=allowed_ports)
    rows: list[list[Any]] = [
        [payload.get("title") or "Movimientos de bookings"],
        [f"Año {year}"],
        [],
        ["", *MONTH_LABELS_ES, "Total general"],
    ]
    for item in payload.get("type_rows") or []:
        rows.append(
            [
                item.get("kind") or "",
                *(item.get("months") or [0] * 12),
                item.get("total") or 0,
            ]
        )
    rows.append(
        [
            "Total general",
            *(payload.get("type_month_totals") or [0] * 12),
            payload.get("type_grand_total") or 0,
        ]
    )
    rows.append([])
    rows.append(["", *MONTH_LABELS_ES, "Total general"])
    for block in payload.get("port_blocks") or []:
        rows.append(
            [
                block.get("port_name") or "",
                *(block.get("months") or [0] * 12),
                block.get("total") or 0,
            ]
        )
        for year_row in block.get("years") or []:
            rows.append(
                [
                    year_row.get("year") or "",
                    *(year_row.get("months") or [0] * 12),
                    year_row.get("total") or 0,
                ]
            )
    rows.append(
        [
            "Total general",
            *(payload.get("pax_month_totals") or [0] * 12),
            payload.get("pax_grand_total") or 0,
        ]
    )
    return _csv_bytes(rows)


def build_solicitudes_port_csv(payload: dict[str, Any]) -> bytes:
    rows: list[list[Any]] = [
        [payload.get("title") or "RESUMEN"],
    ]
    subtitle = str(payload.get("subtitle") or "").strip()
    if subtitle:
        rows.append([subtitle])
    rows.append([])

    for block in payload.get("year_blocks") or []:
        rows.append([block.get("title") or ""])
        rows.append(
            ["Ship", "Port", "Arrival", "Hora llegada", "Hora salida", "Pax"]
        )
        for item in block.get("rows") or []:
            rows.append(
                [
                    item.get("ship"),
                    item.get("port"),
                    item.get("arrival_label"),
                    item.get("eta"),
                    item.get("etd"),
                    item.get("pax"),
                ]
            )
        rows.append(["", "", "", "", "", block.get("pax_total") or 0])
        rows.append([])

    carrier_rows = list(
        payload.get("carrier_by_year") or payload.get("nuevas_solicitadas") or []
    )
    if carrier_rows:
        rows.append(["Año", "PAX naviera/grupo"])
        for item in carrier_rows:
            rows.append([item.get("year"), item.get("pax")])

    return _csv_bytes(rows)
