"""Landscape monthly calendar — positions × weekdays (Beto occupancy)."""

from __future__ import annotations

from io import BytesIO

from django.utils import timezone
from reportlab.lib.colors import white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from apps.bookings.services.arrivals_pdf.calendar_block import (
    DAYS,
    MonthBlock,
    build_month_block,
    build_week_block,
    week_dates,
)
from apps.bookings.services.arrivals_pdf.chrome import (
    FOOTER_BAR_H,
    GRID,
    INK,
    MARGIN,
    STEEL,
    draw_flyer_header,
    draw_table_footer_bar,
    fit_text,
    port_subtitle,
)
from apps.bookings.services.arrivals_pdf.labels import arrivals_title
from apps.bookings.services.arrivals_pdf.logo import port_logo_reader
from apps.bookings.services.arrivals_pdf.list_data import group_bookings_by_port
from apps.bookings.services.arrivals_pdf.month_grid import group_port_months
from apps.bookings.services.arrivals_pdf.overview import (
    ExportOverview,
    draw_overview_band,
)

HEADER_H = 1.7 * cm
HEAD_H = 14.0
DATE_H = 12.0
POS_H = 11.0
COUNT_W = 0.9 * cm
POS_W = 1.35 * cm


def build_arrivals_calendar_pdf(
    bookings: list,
    *,
    overview: ExportOverview | None = None,
    mode: str = "monthly",
    date_from=None,
    date_to=None,
    ports: list | None = None,
) -> bytes:
    page_w, page_h = landscape(A4)
    updated = timezone.localdate()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    weekly = mode == "weekly" and date_from is not None
    if weekly:
        days = week_dates(date_from, date_to)
        grouped = group_bookings_by_port(bookings)
        by_port = {port.id: rows for port, rows in grouped}
        port_list = list(ports or [port for port, _rows in grouped])
        for port in port_list:
            block = build_week_block(port, days, by_port.get(port.id, []))
            _draw_month(
                pdf,
                page_w,
                page_h,
                logo=port_logo_reader(port),
                subtitle=port_subtitle(port),
                block=block,
                updated=updated,
                overview=overview,
                weekly=True,
            )
            pdf.showPage()
    else:
        for port, year, month, rows in group_port_months(bookings):
            block = build_month_block(port, year, month, rows)
            _draw_month(
                pdf,
                page_w,
                page_h,
                logo=port_logo_reader(port),
                subtitle=port_subtitle(port),
                block=block,
                updated=updated,
                overview=overview,
            )
            pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _draw_month(
    pdf: canvas.Canvas,
    page_w: float,
    page_h: float,
    *,
    logo,
    subtitle: str,
    block: MonthBlock,
    updated,
    overview: ExportOverview | None = None,
    weekly: bool = False,
) -> None:
    table_w = page_w - 2 * MARGIN
    day_w = max(1.2 * cm, (table_w - COUNT_W - POS_W) / DAYS)
    col_w = [COUNT_W, POS_W, *([day_w] * DAYS)]
    title = f"Arribos {block.title}" if weekly else arrivals_title(block.year, block.month)
    draw_flyer_header(
        pdf,
        page_w,
        page_h,
        logo=logo,
        title=title,
        subtitle=subtitle,
        total=block.total,
        title_size=14 if weekly else 18,
        logo_h=1.25 * cm,
    )
    x = MARGIN
    y = page_h - MARGIN - HEADER_H
    y = draw_overview_band(pdf, x, y, table_w, overview)
    y = _draw_header(pdf, x, y, col_w, block.title, block.weekday_labels)
    pos_h = 22.0 if weekly else POS_H
    date_h = 16.0 if weekly else DATE_H
    for week in block.weeks:
        y = _draw_week(pdf, x, y, col_w, week, pos_h=pos_h, date_h=date_h)
    draw_table_footer_bar(
        pdf, x, MARGIN, table_w, updated=updated, kind="calendar"
    )


def _draw_header(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    col_w: list[float],
    title: str,
    weekday_labels: tuple[str, ...],
) -> float:
    table_w = sum(col_w)
    pdf.setFillColor(STEEL)
    pdf.rect(x, y - HEAD_H, table_w, HEAD_H, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(x + col_w[0] / 2, y - HEAD_H + 4.2, "#")
    pdf.drawCentredString(x + col_w[0] + col_w[1] / 2, y - HEAD_H + 4.2, "Pos.")
    cx = x + col_w[0] + col_w[1]
    for width, label in zip(col_w[2:], weekday_labels, strict=True):
        pdf.drawCentredString(cx + width / 2, y - HEAD_H + 4.2, label)
        cx += width
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(0.6)
    pdf.rect(x, y - HEAD_H, table_w, HEAD_H, fill=0, stroke=1)
    y -= HEAD_H
    pdf.setFillColor(STEEL)
    pdf.rect(x, y - DATE_H, table_w, DATE_H, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(x + table_w / 2, y - DATE_H + 3.4, title)
    pdf.rect(x, y - DATE_H, table_w, DATE_H, fill=0, stroke=1)
    return y - DATE_H


def _draw_week(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    col_w: list[float],
    week,
    *,
    pos_h: float = POS_H,
    date_h: float = DATE_H,
) -> float:
    table_w = sum(col_w)
    pdf.setFillColor(white)
    pdf.rect(x, y - date_h, table_w, date_h, fill=1, stroke=0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(x + col_w[0] / 2, y - date_h + 3.2, str(week.count))
    cx = x + col_w[0] + col_w[1]
    pdf.setFont("Helvetica", 6.4)
    for width, stamp in zip(col_w[2:], week.dates, strict=True):
        if stamp:
            pdf.drawCentredString(cx + width / 2, y - date_h + 3.2, stamp)
        cx += width
    _stroke(pdf, x, y - date_h, col_w, date_h)
    y -= date_h
    for label, cells in week.rows:
        pdf.setFillColor(white)
        pdf.rect(x, y - pos_h, table_w, pos_h, fill=1, stroke=0)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 6.5)
        pdf.drawCentredString(
            x + col_w[0] + col_w[1] / 2, y - pos_h / 2 - 2.0, label
        )
        cx = x + col_w[0] + col_w[1]
        pdf.setFont("Helvetica", 7 if pos_h > 14 else 6.2)
        for width, value in zip(col_w[2:], cells, strict=True):
            text = fit_text(pdf, value, width - 4)
            pdf.drawCentredString(cx + width / 2, y - pos_h / 2 - 2.0, text)
            cx += width
        _stroke(pdf, x, y - pos_h, col_w, pos_h)
        y -= pos_h
    return y


def _stroke(
    pdf: canvas.Canvas, x: float, y: float, col_w: list[float], height: float
) -> None:
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(0.45)
    total = sum(col_w)
    pdf.rect(x, y, total, height, fill=0, stroke=1)
    cx = x
    for width in col_w[:-1]:
        cx += width
        pdf.line(cx, y, cx, y + height)
