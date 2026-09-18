"""PDF builders for structured ReportsView exports (Platypus tables)."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.bookings.services.report_exports.availability import _availability_export_rows
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
from apps.bookings.services.report_exports.report_theme import (
    BODY_SIZE,
    GRID as GRID_HEX,
    GROWTH_NEG as GROWTH_NEG_HEX,
    GROWTH_POS as GROWTH_POS_HEX,
    HEADER_SIZE,
    NAVY as NAVY_HEX,
    NAVY_MID as NAVY_MID_HEX,
    PDF_TABLE_SIZE,
    SECTION_SIZE,
    SKY as SKY_HEX,
    SKY_LIGHT as SKY_LIGHT_HEX,
    SUBTITLE_SIZE,
    TEXT as TEXT_HEX,
    TITLE_SIZE,
    WHITE as WHITE_HEX,
)
from apps.catalogs.models import Port

NAVY = colors.HexColor(f"#{NAVY_HEX}")
NAVY_MID = colors.HexColor(f"#{NAVY_MID_HEX}")
SKY = colors.HexColor(f"#{SKY_HEX}")
SKY_LIGHT = colors.HexColor(f"#{SKY_LIGHT_HEX}")
WHITE = colors.HexColor(f"#{WHITE_HEX}")
GROWTH_POS = colors.HexColor(f"#{GROWTH_POS_HEX}")
GROWTH_NEG = colors.HexColor(f"#{GROWTH_NEG_HEX}")
TEXT = colors.HexColor(f"#{TEXT_HEX}")
GRID = colors.HexColor(f"#{GRID_HEX}")


def _styles():
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=TITLE_SIZE,
        textColor=NAVY,
        spaceBefore=0,
        spaceAfter=0,
        leading=TITLE_SIZE + 2,
        alignment=TA_LEFT,
    )
    subtitle = ParagraphStyle(
        "ReportSubtitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=SUBTITLE_SIZE,
        textColor=NAVY_MID,
        spaceBefore=0,
        spaceAfter=0,
        leading=SUBTITLE_SIZE + 2,
        alignment=TA_LEFT,
    )
    section = ParagraphStyle(
        "ReportSection",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=SECTION_SIZE,
        textColor=WHITE,
        spaceBefore=0,
        spaceAfter=0,
        alignment=TA_LEFT,
    )
    body = ParagraphStyle(
        "ReportBody",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=BODY_SIZE,
        textColor=TEXT,
        spaceBefore=0,
        spaceAfter=0,
    )
    return title, subtitle, section, body


def _banner_flowables(title: str, subtitle: str | None, col_count: int):
    """Excel-parity banner: sky fill, title (+ subtitle), no outer box, no spacer row."""
    title_s, subtitle_s, _, _ = _styles()
    rows = [[Paragraph(title, title_s)]]
    if subtitle and subtitle.strip():
        rows.append([Paragraph(subtitle.strip(), subtitle_s)])
    # Stretch to usable page width like Excel col_span.
    banner = Table(rows, colWidths=["*"])
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SKY_LIGHT),
                ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                # Match side density: less air above the title.
                ("TOPPADDING", (0, 0), (0, 0), 4),
                ("BOTTOMPADDING", (0, 0), (0, 0), 2 if subtitle else 4),
                ("TOPPADDING", (0, 1), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    _ = col_count
    return [banner]


def _data_table(
    data: list[list[Any]],
    *,
    emphasize_rows: set[int] | None = None,
    emphasize_last: bool = False,
) -> Table:
    """
    Excel-parity data table: navy header band, sky label column,
    subtle right/bottom grid (no outer BOX frame), total/group highlight.
    """
    table = Table(data, repeatRows=1)
    style_cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), HEADER_SIZE),
        ("FONTSIZE", (0, 1), (-1, -1), PDF_TABLE_SIZE),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        # Subtle grid like Excel BORDER_GRID (right + bottom), no outer BOX.
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, GRID),
        ("LINEAFTER", (0, 0), (-2, -1), 0.4, GRID),
    ]
    # Label column sky fill (Excel FILL_ROW_LABEL) for body rows.
    if len(data) > 1:
        style_cmds.append(("BACKGROUND", (0, 1), (0, -1), SKY))
        style_cmds.append(("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"))
        style_cmds.append(("TEXTCOLOR", (0, 1), (0, -1), NAVY))
        # Alternating data cells (not label col).
        for r in range(1, len(data)):
            if r % 2 == 0:
                style_cmds.append(("BACKGROUND", (1, r), (-1, r), SKY_LIGHT))

    emphasized = set(emphasize_rows or ())
    if emphasize_last and len(data) > 1:
        emphasized.add(len(data) - 1)
    for r in emphasized:
        if 0 < r < len(data):
            style_cmds.append(("BACKGROUND", (0, r), (-1, r), SKY_LIGHT))
            style_cmds.append(("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"))
            style_cmds.append(("TEXTCOLOR", (0, r), (-1, r), NAVY))

    table.setStyle(TableStyle(style_cmds))
    return table


def _build_doc(story: list, *, landscape_mode: bool = True) -> bytes:
    buf = BytesIO()
    pagesize = landscape(A4) if landscape_mode else A4
    side = 1.2 * cm
    # Top: same visual density as sides (less page air + compact banner).
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        leftMargin=side,
        rightMargin=side,
        topMargin=0.65 * cm,
        bottomMargin=side,
    )
    doc.build(story)
    return buf.getvalue()


def _matrix_pdf(
    *,
    calls_title: str,
    pax_title: str,
    report: dict[str, Any],
) -> bytes:
    subtitle_parts = []
    if report.get("date_from") and report.get("date_to"):
        subtitle_parts.append(f"{report['date_from']} → {report['date_to']}")
    note = report.get("note") or ""
    if report.get("without_lta"):
        note = f"{note} Sin LTA.".strip() if note else "Sin LTA."
    if note:
        subtitle_parts.append(note)
    subtitle = " · ".join(subtitle_parts) or None

    story: list = []
    for metric_key, title in (("calls", calls_title), ("pax", pax_title)):
        story.extend(_banner_flowables(title, subtitle, 14))
        for section in report.get("sections") or []:
            _, _, section_style, _ = _styles()
            sec = Table(
                [[Paragraph(str(section.get("label") or ""), section_style)]],
            )
            sec.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), NAVY_MID),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(sec)
            data = [["AÑO", *MONTH_LABELS, "TOTAL"]]
            for data_row in section.get(metric_key) or []:
                label = (
                    "TOTAL"
                    if data_row.get("year") == "total"
                    else str(data_row.get("year") or "")
                )
                data.append(
                    [
                        label,
                        *(data_row.get("months") or []),
                        data_row.get("total") or 0,
                    ]
                )
            story.append(_data_table(data, emphasize_last=True))
            story.append(Spacer(1, 0.25 * cm))
        story.append(Spacer(1, 0.3 * cm))
    return _build_doc(story)


def build_ports_totals_matrix_pdf(**kwargs) -> bytes:
    report = build_ports_totals_matrix(**kwargs)
    return _matrix_pdf(
        calls_title="CALL SUMMARY ITM PORTS",
        pax_title="PASSENGER SUMMARY ITM PORTS",
        report=report,
    )


def build_port_carrier_matrix_pdf(**kwargs) -> bytes:
    report = build_port_carrier_matrix(**kwargs)
    port_name = report["port"]["name"]
    return _matrix_pdf(
        calls_title=f"CALL SUMMARY {port_name.upper()}",
        pax_title=f"PASSENGER SUMMARY {port_name.upper()}",
        report=report,
    )


def build_port_trends_pdf(**kwargs) -> bytes:
    report = build_port_trends(**kwargs)
    years = report["years"]
    subtitle_parts = []
    if report.get("date_from") and report.get("date_to"):
        subtitle_parts.append(f"{report['date_from']} → {report['date_to']}")
    note = report.get("note") or ""
    if report.get("without_lta"):
        note = f"{note} Sin LTA.".strip() if note else "Sin LTA."
    if note:
        subtitle_parts.append(note)
    subtitle = " · ".join(subtitle_parts) or None

    header = ["Grupo / Naviera"]
    for year in years:
        header.extend([f"{year} SHIPS", f"{year} PAX"])
    header.extend(["Total SHIPS", "Total PAX"])
    trends_cols = len(header)

    story: list = []
    story.extend(
        _banner_flowables(
            f"TRENDS — {report['port']['name'].upper()}",
            subtitle,
            trends_cols,
        )
    )

    data: list[list[Any]] = [header]
    emphasize: set[int] = set()

    def append_metric(label: str, item: dict[str, Any], *, bold: bool = False) -> None:
        values: list[Any] = [label]
        for cell in item.get("by_year") or []:
            values.extend([cell.get("ships") or "", cell.get("pax") or ""])
        values.extend([item.get("total_ships") or "", item.get("total_pax") or ""])
        data.append(values)
        if bold:
            emphasize.add(len(data) - 1)

    for group in report.get("groups") or []:
        append_metric(group["name"], group, bold=True)
        for line in group.get("lines") or []:
            append_metric(f"  {line['name']}", line)
    totals = report.get("totals")
    if totals:
        append_metric("TOTAL", totals, bold=True)

    story.append(_data_table(data, emphasize_rows=emphasize))
    story.append(Spacer(1, 0.35 * cm))

    growth_cols = 1 + len(years)
    story.extend(
        _banner_flowables("GROWTH PERCENTAGE (PAX YoY)", subtitle, growth_cols)
    )
    growth: list[list[Any]] = [["Grupo / Naviera", *[str(y) for y in years]]]
    growth_emphasize: set[int] = set()

    def append_growth(label: str, item: dict[str, Any], *, bold: bool = False) -> None:
        row = [label]
        for g in item.get("growth") or []:
            pct = g.get("pct")
            row.append("" if pct is None else f"{pct}%")
        growth.append(row)
        if bold:
            growth_emphasize.add(len(growth) - 1)

    for group in report.get("groups") or []:
        append_growth(group["name"], group, bold=True)
        for line in group.get("lines") or []:
            append_growth(f"  {line['name']}", line)
    if totals:
        append_growth("TOTAL", totals, bold=True)

    gtable = _data_table(growth, emphasize_rows=growth_emphasize)
    cmds = []
    for r_idx, row in enumerate(growth[1:], start=1):
        for c_idx, val in enumerate(row[1:], start=1):
            if isinstance(val, str) and val.endswith("%"):
                try:
                    num = float(val[:-1])
                except ValueError:
                    continue
                if num > 0:
                    cmds.append(("TEXTCOLOR", (c_idx, r_idx), (c_idx, r_idx), GROWTH_POS))
                elif num < 0:
                    cmds.append(("TEXTCOLOR", (c_idx, r_idx), (c_idx, r_idx), GROWTH_NEG))
    if cmds:
        gtable.setStyle(TableStyle(cmds))
    story.append(gtable)
    return _build_doc(story)


def build_booking_movements_pdf(*, year: int, allowed_ports=None) -> bytes:
    payload = build_booking_movements_report(year=year, allowed_ports=allowed_ports)
    note = str(payload.get("note") or "").strip()
    subtitle = f"Año {year}" + (f" · {note}" if note else "")
    story = _banner_flowables(
        str(payload.get("title") or "Movimientos de bookings"),
        subtitle,
        14,
    )

    header = ["", *MONTH_LABELS_ES, "Total general"]
    type_data: list[list[Any]] = [header]
    for item in payload.get("type_rows") or []:
        type_data.append(
            [
                item.get("kind") or "",
                *(item.get("months") or [0] * 12),
                item.get("total") or 0,
            ]
        )
    type_data.append(
        [
            "Total general",
            *(payload.get("type_month_totals") or [0] * 12),
            payload.get("type_grand_total") or 0,
        ]
    )
    story.append(_data_table(type_data, emphasize_last=True))
    story.append(Spacer(1, 0.4 * cm))

    pax_data: list[list[Any]] = [header]
    for block in payload.get("port_blocks") or []:
        pax_data.append(
            [
                block.get("port_name") or "",
                *(block.get("months") or [0] * 12),
                block.get("total") or 0,
            ]
        )
        for year_row in block.get("years") or []:
            pax_data.append(
                [
                    str(year_row.get("year") or ""),
                    *(year_row.get("months") or [0] * 12),
                    year_row.get("total") or 0,
                ]
            )
    pax_data.append(
        [
            "Total general",
            *(payload.get("pax_month_totals") or [0] * 12),
            payload.get("pax_grand_total") or 0,
        ]
    )
    story.append(_data_table(pax_data, emphasize_last=True))
    return _build_doc(story)


def build_solicitudes_port_pdf(payload: dict[str, Any]) -> bytes:
    title = str(payload.get("title") or "RESUMEN")
    subtitle = str(payload.get("subtitle") or "").strip() or None
    story = _banner_flowables(title, subtitle, 6)

    for block in payload.get("year_blocks") or []:
        data: list[list[Any]] = [
            ["Ship", "Port", "Arrival", "Hora llegada", "Hora salida", "Pax"]
        ]
        for item in block.get("rows") or []:
            data.append(
                [
                    item.get("ship") or "",
                    item.get("port") or "",
                    item.get("arrival_label") or "",
                    item.get("eta") or "",
                    item.get("etd") or "",
                    item.get("pax") or 0,
                ]
            )
        data.append(["", "", "", "", "Total", block.get("pax_total") or 0])
        _, _, section_style, _ = _styles()
        sec = Table(
            [[Paragraph(str(block.get("title") or ""), section_style)]],
        )
        sec.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), NAVY_MID),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(sec)
        story.append(Spacer(1, 0.1 * cm))
        story.append(_data_table(data, emphasize_last=True))
        story.append(Spacer(1, 0.3 * cm))

    return _build_doc(story, landscape_mode=False)


def build_availability_chart_pdf(**kwargs) -> bytes:
    header, rows = _availability_export_rows(**kwargs)
    port = Port.objects.get(pk=kwargs["port_id"])
    subtitle = (
        f"{port.name} · {kwargs['date_from'].isoformat()} → "
        f"{kwargs['date_to'].isoformat()}"
    )
    story = _banner_flowables("Availability Chart", subtitle, len(header))
    data = [list(header), *[list(r) for r in rows]]
    story.append(_data_table(data))
    return _build_doc(story)


def build_weekly_report_pdf(payload: dict[str, Any]) -> bytes:
    """Reporte Semanal — Sem. badge + port bands + metric rows."""
    call_years = list(payload.get("call_years") or [])
    title = str(
        payload.get("title") or payload.get("report_name") or "Reporte Semanal"
    )
    week = payload.get("week")
    subtitle = (
        f"Sem. {week} · {payload.get('week_start')} → {payload.get('week_end')}"
    )
    story = _banner_flowables(title, subtitle, 1 + len(call_years))

    week_tbl = Table(
        [[Paragraph(f"<b>Sem.</b><br/>{week}", _styles()[1])]],
        colWidths=[2.2 * cm],
    )
    week_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FCE4D6")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(week_tbl)
    story.append(Spacer(1, 0.25 * cm))

    def _cell(n: int) -> str:
        if not n:
            return ""
        return f"{n:,}"

    def _total_cell(n: int) -> str:
        return f"{n:,}"

    header = ["PUERTO", *[str(y) for y in call_years]]
    data: list[list[Any]] = [header]
    port_row_idxs: list[int] = []
    metric_row_idxs: list[int] = []

    for port in payload.get("ports") or []:
        label = str(port.get("port_name") or "").strip()
        totals = list(port.get("totals") or [])
        port_row_idxs.append(len(data))
        data.append(
            [
                label,
                *[
                    _total_cell(int(totals[i] if i < len(totals) else 0))
                    for i in range(len(call_years))
                ],
            ]
        )
        for metric in port.get("metrics") or []:
            values = list(metric.get("values") or [])
            metric_row_idxs.append(len(data))
            data.append(
                [
                    str(metric.get("label") or ""),
                    *[
                        _cell(int(values[i] if i < len(values) else 0))
                        for i in range(len(call_years))
                    ],
                ]
            )

    table = Table(data, repeatRows=1)
    cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.white),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), PDF_TABLE_SIZE),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Oblique"),
    ]
    for r in port_row_idxs:
        cmds.append(("BACKGROUND", (0, r), (-1, r), NAVY))
        cmds.append(("TEXTCOLOR", (0, r), (-1, r), WHITE))
        cmds.append(("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"))
    for r in metric_row_idxs:
        cmds.append(("TEXTCOLOR", (0, r), (0, r), colors.HexColor("#5B9BD5")))
        cmds.append(("FONTNAME", (0, r), (0, r), "Helvetica-Oblique"))
        cmds.append(("TEXTCOLOR", (1, r), (-1, r), TEXT))
    table.setStyle(TableStyle(cmds))
    story.append(table)
    return _build_doc(story)
