"""PDF builders for structured ReportsView exports (Platypus tables)."""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any

from django.core.files.storage import default_storage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    KeepTogether,
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


PDF_SIDE_MARGIN = 1.2 * cm


def _page_usable_width(*, landscape_mode: bool = True) -> float:
    pagesize = landscape(A4) if landscape_mode else A4
    return float(pagesize[0]) - 2 * PDF_SIDE_MARGIN


def _stretch_col_widths(
    ncols: int,
    *,
    landscape_mode: bool = True,
    first_col_ratio: float = 0.28,
    usable: float | None = None,
) -> list[float]:
    """Force tables to usable page width (avoids narrow content-sized PDFs)."""
    usable_w = (
        usable if usable is not None else _page_usable_width(landscape_mode=landscape_mode)
    )
    if ncols <= 1:
        return [usable_w]
    first_ratio = min(max(first_col_ratio, 0.15), 0.45)
    first = usable_w * first_ratio
    rest = (usable_w - first) / (ncols - 1)
    return [first] + [rest] * (ncols - 1)


def _fmt_matrix_num(value: Any) -> str:
    """Thousands separators; decimals only when the value is not a whole number."""
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == 0:
        return "—"
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number)):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _logo_flowable(section: dict[str, Any], size: float = 0.9 * cm) -> Image | None:
    raw: bytes | None = None
    path = section.get("logo_path")
    name = section.get("logo_name")
    if path and os.path.isfile(path):
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
        except OSError:
            raw = None
    if raw is None and name:
        try:
            with default_storage.open(name, "rb") as handle:
                raw = handle.read()
        except Exception:
            raw = None
    if not raw:
        return None
    head = raw[:400].lstrip()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return None
    bio = BytesIO(raw)
    try:
        reader = ImageReader(bio)
        width_px, height_px = reader.getSize()
        if not width_px or not height_px:
            return None
        if width_px >= height_px:
            width, height = size, size * (height_px / width_px)
        else:
            height, width = size, size * (width_px / height_px)
        bio.seek(0)
        image = Image(bio, width=width, height=height)
        image.hAlign = "LEFT"
        return image
    except Exception:
        return None


def _week_badge_flowable(week: int | str | None) -> Table:
    """Peach Sem. card — same language as HTML WeeklyReportSection actions."""
    _, subtitle_s, _, _ = _styles()
    badge = Table(
        [[Paragraph(f"<b>Sem.</b><br/>{week if week is not None else ''}", subtitle_s)]],
        colWidths=[2.4 * cm],
    )
    badge.setStyle(
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
    return badge


def _banner_flowables(
    title: str,
    subtitle: str | None,
    col_count: int,
    *,
    right_flowable: Any | None = None,
    landscape_mode: bool = True,
):
    """Excel-parity banner: sky fill, title (+ subtitle), optional right badge."""
    title_s, subtitle_s, _, _ = _styles()
    left_rows = [[Paragraph(title, title_s)]]
    if subtitle and subtitle.strip():
        left_rows.append([Paragraph(subtitle.strip(), subtitle_s)])
    usable = _page_usable_width(landscape_mode=landscape_mode)
    left = Table(left_rows, colWidths=["*"])
    left.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SKY_LIGHT),
                ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (0, 0), 4),
                ("BOTTOMPADDING", (0, 0), (0, 0), 2 if subtitle else 4),
                ("TOPPADDING", (0, 1), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    if right_flowable is None:
        banner = Table([[left]], colWidths=[usable])
        banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SKY_LIGHT),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
    else:
        badge_w = 2.6 * cm
        banner = Table(
            [[left, right_flowable]],
            colWidths=[usable - badge_w, badge_w],
        )
        banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SKY_LIGHT),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 4),
                    ("LEFTPADDING", (1, 0), (1, 0), 0),
                    ("RIGHTPADDING", (1, 0), (1, 0), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
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
    landscape_mode: bool = True,
    first_col_ratio: float = 0.28,
    usable_width: float | None = None,
) -> Table:
    """
    Excel-parity data table: navy header band, sky label column,
    subtle right/bottom grid (no outer BOX frame), total/group highlight.
    Always stretches to usable page width.
    """
    ncols = max((len(row) for row in data), default=1)
    widths = _stretch_col_widths(
        ncols,
        landscape_mode=landscape_mode,
        first_col_ratio=first_col_ratio,
        usable=usable_width,
    )
    table = Table(data, repeatRows=1, colWidths=widths)
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
    # Top: same visual density as sides (less page air + compact banner).
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        leftMargin=PDF_SIDE_MARGIN,
        rightMargin=PDF_SIDE_MARGIN,
        topMargin=0.65 * cm,
        bottomMargin=PDF_SIDE_MARGIN,
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

    # Same order as HTML ReportDualMatrix: per section, calls then pax.
    _ = pax_title
    story: list = _banner_flowables(
        str(report.get("title") or calls_title),
        subtitle,
        14,
    )
    _, _, _, body_style = _styles()
    title_style = ParagraphStyle(
        "MatrixPortTitle",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=SECTION_SIZE,
        textColor=NAVY,
        leading=SECTION_SIZE + 2,
    )
    kicker_style = ParagraphStyle(
        "MatrixPortKicker",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=7,
        textColor=NAVY_MID,
        leading=9,
    )
    metric_style = ParagraphStyle(
        "MatrixMetricLabel",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=SECTION_SIZE - 1,
        textColor=NAVY,
        leading=SECTION_SIZE + 1,
    )

    usable = _page_usable_width()
    inset = 8
    inner = usable - 2 * inset

    def _section_kicker(section: dict[str, Any]) -> str:
        if section.get("is_total") and not section.get("logo") and not section.get(
            "logo_name"
        ):
            return "CONSOLIDADO"
        if section.get("logo_kind") == "shipping_line":
            return "NAVIERA"
        if section.get("is_total"):
            return "CONSOLIDADO"
        return "PUERTO"

    def _port_header(section: dict[str, Any]) -> Table:
        kicker = Paragraph(_section_kicker(section), kicker_style)
        title = Paragraph(str(section.get("label") or ""), title_style)
        labels = Table([[kicker], [title]], colWidths=["*"])
        labels.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        logo = _logo_flowable(section)
        if logo:
            logo_w = 1.15 * cm
            header = Table([[logo, labels]], colWidths=[logo_w, inner - logo_w])
        else:
            header = Table([[labels]], colWidths=[inner])
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return header

    def _metric_banner(label: str) -> Table:
        banner = Table([[Paragraph(str(label), metric_style)]], colWidths=[inner])
        banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SKY),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return banner

    def _metric_table(section: dict[str, Any], metric_key: str) -> Table:
        data = [["AÑO", *MONTH_LABELS, "TOTAL"]]
        for data_row in section.get(metric_key) or []:
            label = (
                "TOTAL"
                if data_row.get("year") == "total"
                else str(data_row.get("year") or "")
            )
            months = [_fmt_matrix_num(value) for value in (data_row.get("months") or [])]
            data.append([label, *months, _fmt_matrix_num(data_row.get("total") or 0)])
        return _data_table(
            data,
            emphasize_last=True,
            first_col_ratio=0.12,
            usable_width=inner,
        )

    def _port_block(section: dict[str, Any]) -> Table:
        inner_table = Table(
            [
                [_port_header(section)],
                [_metric_banner("Call summary")],
                [_metric_table(section, "calls")],
                [_metric_banner("Passenger summary")],
                [_metric_table(section, "pax")],
            ],
            colWidths=[inner],
        )
        inner_table.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 6),
                    ("TOPPADDING", (0, 1), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, GRID),
                ]
            )
        )
        card = Table([[inner_table]], colWidths=[usable])
        card.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.15, NAVY_MID),
                    ("BACKGROUND", (0, 0), (-1, -1), SKY_LIGHT),
                    ("LEFTPADDING", (0, 0), (-1, -1), inset),
                    ("RIGHTPADDING", (0, 0), (-1, -1), inset),
                    ("TOPPADDING", (0, 0), (-1, -1), inset),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), inset),
                ]
            )
        )
        return card

    for section in report.get("sections") or []:
        story.append(KeepTogether([_port_block(section), Spacer(1, 0.38 * cm)]))
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
    story = _banner_flowables(title, subtitle, 6, landscape_mode=False)

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
        story.append(
            _data_table(data, emphasize_last=True, landscape_mode=False)
        )
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
    """Reporte Semanal — banner + Sem. badge (right) + wide grid table."""
    call_years = list(payload.get("call_years") or [])
    title = str(
        payload.get("title") or payload.get("report_name") or "Reporte Semanal"
    )
    week = payload.get("week")
    subtitle = f"{payload.get('week_start')} → {payload.get('week_end')}"
    story = _banner_flowables(
        title,
        subtitle,
        1 + len(call_years),
        right_flowable=_week_badge_flowable(week),
        landscape_mode=False,
    )

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

    ncols = len(header)
    widths = _stretch_col_widths(
        ncols, landscape_mode=False, first_col_ratio=0.32
    )
    table = Table(data, repeatRows=1, colWidths=widths)
    cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), PDF_TABLE_SIZE),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, GRID),
        ("LINEAFTER", (0, 0), (-2, -1), 0.4, GRID),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, GRID),
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
    return _build_doc(story, landscape_mode=False)


