"""PDF for Panorama Navieras — KPI cards + donut + year matrix (HTML parity)."""

from __future__ import annotations

from typing import Any

from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from apps.bookings.services.report_exports.pdf_reports import (
    GRID,
    NAVY,
    NAVY_MID,
    SKY,
    SKY_LIGHT,
    TEXT,
    WHITE,
    _banner_flowables,
    _build_doc,
    _logo_flowable,
    _page_usable_width,
    _styles,
)
from apps.bookings.services.report_exports.report_theme import (
    MUTED as MUTED_HEX,
    PDF_TABLE_SIZE,
    SECTION_SIZE,
)

MUTED = colors.HexColor(f"#{MUTED_HEX}")

PORT_SHARE_COLORS = (
    "#3478B5",
    "#0D9488",
    "#7C3AED",
    "#CA8A04",
    "#E11D48",
    "#64748B",
)

KPI_CARDS = (
    ("calls", "#3478B5", "#E8F2FA"),
    ("pax", "#0D9488", "#E6F6F4"),
    ("ports", "#7C3AED", "#F3EAFD"),
    ("share", "#CA8A04", "#FBF3DE"),
)


def _fmt_int(value: Any) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    return f"{number:,}"


def _fmt_compact_pax(value: Any) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    if abs(number) >= 1_000_000:
        compact = f"{number / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{compact} M"
    if abs(number) >= 10_000:
        compact = f"{number / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{compact} mil"
    return f"{number:,}"


def _kpi_styles():
    _, _, _, body = _styles()
    label = ParagraphStyle(
        "PanoramaKpiLabel",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=6.5,
        textColor=MUTED,
        leading=8,
        alignment=TA_LEFT,
    )
    value = ParagraphStyle(
        "PanoramaKpiValue",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=NAVY,
        leading=19,
        alignment=TA_LEFT,
    )
    hint = ParagraphStyle(
        "PanoramaKpiHint",
        parent=body,
        fontName="Helvetica",
        fontSize=7,
        textColor=MUTED,
        leading=9,
        alignment=TA_LEFT,
    )
    return label, value, hint


def _kpi_shell(inner: Table, width: float, accent: str, tint: str) -> Table:
    card = Table([[inner]], colWidths=[width])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tint)),
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("LINEABOVE", (0, 0), (-1, 0), 2.6, colors.HexColor(accent)),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return card


def _plain_kpi_card(
    label: str,
    value: str,
    hint: str,
    *,
    width: float,
    accent: str,
    tint: str,
) -> Table:
    label_s, value_s, hint_s = _kpi_styles()
    inner = Table(
        [
            [Paragraph(label, label_s)],
            [Paragraph(value, value_s)],
            [Paragraph(hint or " ", hint_s)],
        ],
        colWidths=[width - 16],
    )
    inner.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 3),
                ("BOTTOMPADDING", (0, 1), (0, 1), 3),
                ("BOTTOMPADDING", (0, 2), (0, 2), 0),
            ]
        )
    )
    return _kpi_shell(inner, width, accent, tint)


def _donut_drawing(share: list[dict[str, Any]], size: float) -> Drawing | None:
    values = [float(item.get("share_pct") or 0) for item in share]
    values = [v for v in values if v > 0]
    if not values:
        return None
    drawing = Drawing(size, size)
    pie = Pie()
    pie.x = 2
    pie.y = 2
    pie.width = size - 4
    pie.height = size - 4
    pie.data = values
    pie.labels = [""] * len(values)
    pie.simpleLabels = 0
    pie.sideLabels = 0
    pie.innerRadiusFraction = 0.58
    pie.slices.strokeWidth = 1.1
    pie.slices.strokeColor = WHITE
    for index, _ in enumerate(values):
        pie.slices[index].fillColor = colors.HexColor(
            PORT_SHARE_COLORS[index % len(PORT_SHARE_COLORS)]
        )
    drawing.add(pie)
    return drawing


def _share_kpi_card(
    share: list[dict[str, Any]],
    hint: str,
    *,
    width: float,
    accent: str,
    tint: str,
) -> Table:
    label_s, value_s, hint_s = _kpi_styles()
    top = share[0] if share else None
    legend_style = ParagraphStyle(
        "PanoramaShareLegend",
        parent=hint_s,
        fontSize=6.5,
        leading=8,
        textColor=TEXT,
    )
    donut = _donut_drawing(share, 1.55 * cm)
    legend_rows: list[list[Any]] = []
    for index, item in enumerate(share[:5]):
        swatch = Table([[""]], colWidths=[0.22 * cm], rowHeights=[0.22 * cm])
        swatch.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        colors.HexColor(
                            PORT_SHARE_COLORS[index % len(PORT_SHARE_COLORS)]
                        ),
                    ),
                    ("BOX", (0, 0), (-1, -1), 0.2, WHITE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        name = str(item.get("port_name") or "")
        pct = item.get("share_pct") or 0
        legend_rows.append(
            [swatch, Paragraph(f"{name}  {pct}%", legend_style)]
        )
    if not legend_rows:
        legend_rows = [[Paragraph("Sin datos", hint_s)]]

    _ = hint
    legend_text_w = max(width - 2.3 * cm, 2.2 * cm)
    legend = Table(legend_rows, colWidths=[0.32 * cm, legend_text_w])
    legend.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, -1), 3),
                ("RIGHTPADDING", (1, 0), (1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    chart_cell = donut if donut is not None else Paragraph("—", value_s)
    center_name = Paragraph(str(top.get("port_name") or "Sin datos"), hint_s)
    center_pct = Paragraph(
        f"{top.get('share_pct')}%" if top else "0%",
        value_s,
    )
    right = Table(
        [[center_name], [center_pct], [legend]],
        colWidths=[width - 1.85 * cm - 16],
    )
    right.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 1),
                ("BOTTOMPADDING", (0, 1), (0, 1), 4),
                ("BOTTOMPADDING", (0, 2), (0, 2), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    body = Table(
        [[chart_cell, right]],
        colWidths=[1.7 * cm, width - 1.7 * cm - 16],
    )
    body.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    inner = Table(
        [
            [Paragraph("Participación por puerto", label_s)],
            [body],
        ],
        colWidths=[width - 16],
    )
    inner.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 5),
                ("BOTTOMPADDING", (0, 1), (0, 1), 0),
            ]
        )
    )
    return _kpi_shell(inner, width, accent, tint)


def _port_label_cell(row: dict[str, Any], style: ParagraphStyle) -> Any:
    name = Paragraph(str(row.get("port_name") or ""), style)
    logo = _logo_flowable(row, size=0.42 * cm)
    if not logo:
        return name
    cell = Table([[logo, name]], colWidths=[0.55 * cm, "*"])
    cell.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 4),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return cell


def _matrix_table(payload: dict[str, Any], usable: float) -> Table:
    years = list(payload.get("years") or [])
    _, _, _, body = _styles()
    port_style = ParagraphStyle(
        "PanoramaPortName",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=PDF_TABLE_SIZE,
        textColor=NAVY,
        leading=PDF_TABLE_SIZE + 2,
    )
    year_style = ParagraphStyle(
        "PanoramaYearHead",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=WHITE,
        alignment=TA_CENTER,
        leading=10,
    )
    sub_style = ParagraphStyle(
        "PanoramaSubHead",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=6.5,
        textColor=NAVY,
        alignment=TA_CENTER,
        leading=8,
    )
    num_style = ParagraphStyle(
        "PanoramaNum",
        parent=body,
        fontName="Helvetica",
        fontSize=PDF_TABLE_SIZE,
        textColor=TEXT,
        alignment=TA_RIGHT,
        leading=PDF_TABLE_SIZE + 1,
    )
    num_bold = ParagraphStyle(
        "PanoramaNumBold",
        parent=num_style,
        fontName="Helvetica-Bold",
        textColor=NAVY,
    )

    header_top: list[Any] = [Paragraph("Puerto", year_style)]
    header_sub: list[Any] = [""]
    for year in years:
        header_top.extend([Paragraph(str(year), year_style), ""])
        header_sub.extend(
            [Paragraph("Arribos", sub_style), Paragraph("PAX", sub_style)]
        )
    header_top.extend([Paragraph("Total", year_style), ""])
    header_sub.extend(
        [Paragraph("Arribos", sub_style), Paragraph("PAX", sub_style)]
    )

    data: list[list[Any]] = [header_top, header_sub]
    for row in payload.get("rows") or []:
        by_year = {cell["year"]: cell for cell in row.get("by_year") or []}
        values: list[Any] = [_port_label_cell(row, port_style)]
        for year in years:
            cell = by_year.get(year) or {}
            values.extend(
                [
                    Paragraph(_fmt_int(cell.get("calls")), num_style),
                    Paragraph(_fmt_int(cell.get("pax")), num_style),
                ]
            )
        values.extend(
            [
                Paragraph(_fmt_int(row.get("total_calls")), num_bold),
                Paragraph(_fmt_int(row.get("total_pax")), num_bold),
            ]
        )
        data.append(values)

    totals = payload.get("totals") or {}
    total_by_year = {cell["year"]: cell for cell in totals.get("by_year") or []}
    total_row: list[Any] = [Paragraph("Total", port_style)]
    for year in years:
        cell = total_by_year.get(year) or {}
        total_row.extend(
            [
                Paragraph(_fmt_int(cell.get("calls")), num_bold),
                Paragraph(_fmt_int(cell.get("pax")), num_bold),
            ]
        )
    total_row.extend(
        [
            Paragraph(_fmt_int(totals.get("total_calls")), num_bold),
            Paragraph(_fmt_int(totals.get("total_pax")), num_bold),
        ]
    )
    data.append(total_row)

    ncols = 1 + len(years) * 2 + 2
    first = min(max(usable * 0.18, 3.1 * cm), 4.2 * cm)
    rest = (usable - first) / max(ncols - 1, 1)
    widths = [first] + [rest] * (ncols - 1)

    table = Table(data, colWidths=widths, repeatRows=2)
    cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), SKY),
        ("SPAN", (0, 0), (0, 1)),
        ("TEXTCOLOR", (0, 0), (0, 1), WHITE),
        ("FONTNAME", (0, 0), (0, 1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (0, 1), NAVY),
        ("ALIGN", (1, 0), (-1, 1), "CENTER"),
        ("ALIGN", (1, 2), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, 1), 3),
        ("TOPPADDING", (0, 2), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 2), (-1, -1), 3),
        ("LINEBELOW", (0, 1), (-1, -2), 0.35, GRID),
        ("LINEAFTER", (0, 0), (-2, -1), 0.35, GRID),
        ("BACKGROUND", (0, 2), (0, -2), SKY),
    ]
    year_col = 1
    for _ in years:
        cmds.append(("SPAN", (year_col, 0), (year_col + 1, 0)))
        year_col += 2
    cmds.append(("SPAN", (year_col, 0), (year_col + 1, 0)))

    for row_idx in range(2, len(data) - 1):
        if row_idx % 2 == 1:
            cmds.append(("BACKGROUND", (1, row_idx), (-1, row_idx), SKY_LIGHT))
    last = len(data) - 1
    cmds.extend(
        [
            ("BACKGROUND", (0, last), (-1, last), SKY_LIGHT),
            ("LINEABOVE", (0, last), (-1, last), 0.8, NAVY_MID),
        ]
    )
    table.setStyle(TableStyle(cmds))
    return table


def _matrix_card(payload: dict[str, Any], usable: float) -> Table:
    _, _, _, body = _styles()
    title_s = ParagraphStyle(
        "PanoramaMatrixTitle",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=SECTION_SIZE,
        textColor=NAVY,
        leading=SECTION_SIZE + 2,
    )
    note_s = ParagraphStyle(
        "PanoramaMatrixNote",
        parent=body,
        fontName="Helvetica",
        fontSize=7.5,
        textColor=MUTED,
        leading=10,
    )
    title = str(
        payload.get("matrix_title")
        or "Arribos y pasajeros totales programados por puerto"
    )
    note = str(payload.get("note") or "").strip()
    header_rows = [[Paragraph(title, title_s)]]
    if note:
        header_rows.append([Paragraph(note, note_s)])
    header = Table(header_rows, colWidths=[usable - 16])
    header.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 3 if note else 0),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 0),
            ]
        )
    )
    inner = Table(
        [[header], [_matrix_table(payload, usable - 16)]],
        colWidths=[usable - 16],
    )
    inner.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 8),
                ("TOPPADDING", (0, 1), (0, 1), 0),
                ("BOTTOMPADDING", (0, 1), (0, 1), 0),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, GRID),
            ]
        )
    )
    card = Table([[inner]], colWidths=[usable])
    card.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, NAVY_MID),
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return card


def build_carrier_panorama_pdf(payload: dict[str, Any]) -> bytes:
    kpis = payload.get("kpis") or {}
    share = list(payload.get("port_share") or [])
    title = str(payload.get("title") or "Panorama Navieras")
    subtitle = str(payload.get("subtitle") or "").strip() or None
    landscape_mode = True

    usable = _page_usable_width(landscape_mode=landscape_mode)
    gap = 0.16 * cm
    card_w = (usable - 3 * gap) / 4
    hint = subtitle or ""
    _, calls_accent, calls_tint = KPI_CARDS[0]
    _, pax_accent, pax_tint = KPI_CARDS[1]
    _, ports_accent, ports_tint = KPI_CARDS[2]
    _, share_accent, share_tint = KPI_CARDS[3]

    story = _banner_flowables(title, subtitle, 4, landscape_mode=landscape_mode)
    story.append(Spacer(1, 0.22 * cm))
    kpi_row = Table(
        [
            [
                _plain_kpi_card(
                    "Arribos totales",
                    _fmt_int(kpis.get("total_calls")),
                    hint,
                    width=card_w,
                    accent=calls_accent,
                    tint=calls_tint,
                ),
                "",
                _plain_kpi_card(
                    "PAX totales",
                    _fmt_compact_pax(kpis.get("total_pax")),
                    hint,
                    width=card_w,
                    accent=pax_accent,
                    tint=pax_tint,
                ),
                "",
                _plain_kpi_card(
                    "Puertos con programación",
                    f"{kpis.get('ports_with_calls') or 0} de {kpis.get('ports_total') or 0}",
                    hint,
                    width=card_w,
                    accent=ports_accent,
                    tint=ports_tint,
                ),
                "",
                _share_kpi_card(
                    share,
                    hint,
                    width=card_w,
                    accent=share_accent,
                    tint=share_tint,
                ),
            ]
        ],
        colWidths=[card_w, gap, card_w, gap, card_w, gap, card_w],
    )
    kpi_row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(kpi_row)
    story.append(Spacer(1, 0.28 * cm))
    story.append(_matrix_card(payload, usable))
    return _build_doc(story, landscape_mode=landscape_mode)
