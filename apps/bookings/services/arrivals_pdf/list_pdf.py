"""Landscape arrivals list flyer — Costa Maya chrome + CALL LIST columns."""

from __future__ import annotations

from io import BytesIO

from django.utils import timezone
from reportlab.lib.colors import white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from apps.bookings.services.arrivals_pdf.chrome import (
    FOOTER_BAR_H,
    GRID,
    HEADER_H,
    INK,
    MARGIN,
    NAVY,
    draw_flyer_header,
    draw_table_footer_bar,
    fit_text,
    port_subtitle,
)
from apps.bookings.services.arrivals_pdf.labels import arrivals_range_title
from apps.bookings.services.arrivals_pdf.overview import (
    ExportOverview,
    draw_overview_band,
)
from apps.bookings.services.arrivals_pdf.list_data import (
    group_bookings_by_port,
    list_center_cols,
    list_col_fracs,
    list_headers,
    list_row_values,
)
from apps.bookings.services.arrivals_pdf.logo import port_logo_reader
from apps.bookings.services.report_exports.common import PAX_BASIS_PLANNED

ROW_H = 12.4
HEAD_H = 14.0


def build_arrivals_list_pdf(
    bookings: list,
    *,
    overview: ExportOverview | None = None,
    pax_basis: str = PAX_BASIS_PLANNED,
    include_cancellation: bool = False,
) -> bytes:
    pagesize = landscape(A4)
    page_w, page_h = pagesize
    usable = page_w - 2 * MARGIN
    col_w = [
        usable * frac
        for frac in list_col_fracs(include_cancellation=include_cancellation)
    ]
    updated = timezone.localdate()

    groups = group_bookings_by_port(bookings)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=pagesize)

    for port, rows in groups:
        logo = port_logo_reader(port)
        start = rows[0].call_date
        end = rows[-1].call_date
        title = arrivals_range_title(start, end)
        subtitle = port_subtitle(port)
        _draw_group_pages(
            pdf,
            page_w,
            page_h,
            col_w,
            logo=logo,
            title=title,
            subtitle=subtitle,
            rows=rows,
            updated=updated,
            overview=overview,
            pax_basis=pax_basis,
            include_cancellation=include_cancellation,
        )

    pdf.save()
    return buffer.getvalue()


def _draw_group_pages(
    pdf: canvas.Canvas,
    page_w: float,
    page_h: float,
    col_w: list[float],
    *,
    logo,
    title: str,
    subtitle: str,
    rows: list,
    updated,
    overview: ExportOverview | None = None,
    pax_basis: str = PAX_BASIS_PLANNED,
    include_cancellation: bool = False,
) -> None:
    top = page_h - MARGIN - HEADER_H
    if overview is not None:
        top -= 0.95 * cm + 4
    table_w = sum(col_w)
    body_h = top - HEAD_H - FOOTER_BAR_H - MARGIN
    max_rows = max(1, int(body_h / ROW_H))
    chunks = [rows[i : i + max_rows] for i in range(0, len(rows), max_rows)] or [[]]
    page_count = len(chunks)
    number = 1
    for page_no, chunk in enumerate(chunks, start=1):
        draw_flyer_header(
            pdf,
            page_w,
            page_h,
            logo=logo,
            title=title,
            subtitle=subtitle,
            total=len(rows) if page_no == 1 else None,
            title_size=16 if len(title) > 36 else 20,
        )
        y = page_h - MARGIN - HEADER_H
        y = draw_overview_band(pdf, MARGIN, y, table_w, overview)
        y = _draw_header_row(
            pdf,
            MARGIN,
            y,
            col_w,
            headers=list_headers(include_cancellation=include_cancellation),
        )
        for booking in chunk:
            _draw_body_row(
                pdf,
                MARGIN,
                y,
                col_w,
                values=list_row_values(
                    booking,
                    number=number,
                    pax_basis=pax_basis,
                    include_cancellation=include_cancellation,
                ),
                center_cols=list_center_cols(
                    include_cancellation=include_cancellation
                ),
            )
            y -= ROW_H
            number += 1
        draw_table_footer_bar(
            pdf,
            MARGIN,
            MARGIN,
            table_w,
            updated=updated,
            kind="list",
            page_no=page_no,
            page_count=page_count,
        )
        pdf.showPage()


def _draw_header_row(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    col_w: list[float],
    *,
    headers: tuple[str, ...],
) -> float:
    pdf.setFillColor(NAVY)
    pdf.rect(x, y - HEAD_H, sum(col_w), HEAD_H, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 7.2)
    cx = x
    for width, label in zip(col_w, headers, strict=True):
        pdf.drawCentredString(
            cx + width / 2, y - HEAD_H + 4.2, fit_text(pdf, label, width - 4)
        )
        cx += width
    _stroke_grid(pdf, x, y - HEAD_H, col_w, HEAD_H)
    return y - HEAD_H


def _draw_body_row(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    col_w: list[float],
    *,
    values: tuple[str, ...],
    center_cols: set[int],
) -> None:
    pdf.setFillColor(white)
    pdf.rect(x, y - ROW_H, sum(col_w), ROW_H, fill=1, stroke=0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 7)
    cx = x
    for i, (width, value) in enumerate(zip(col_w, values, strict=True)):
        text = fit_text(pdf, value, width - 6)
        text_y = y - ROW_H + 3.4
        if i in center_cols:
            pdf.drawCentredString(cx + width / 2, text_y, text)
        else:
            pdf.drawString(cx + 3, text_y, text)
        cx += width
    _stroke_grid(pdf, x, y - ROW_H, col_w, ROW_H)


def _stroke_grid(
    pdf: canvas.Canvas, x: float, y: float, col_w: list[float], height: float
) -> None:
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(0.55)
    total = sum(col_w)
    pdf.rect(x, y, total, height, fill=0, stroke=1)
    cx = x
    for width in col_w[:-1]:
        cx += width
        pdf.line(cx, y, cx, y + height)
