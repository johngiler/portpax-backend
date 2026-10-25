"""Landscape availability flyer — DATE | weekday | berth occupancy, one port per page."""

from __future__ import annotations

from datetime import time
from io import BytesIO

from django.utils import timezone
from reportlab.lib.colors import white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from apps.bookings.services.arrivals_pdf.availability_block import (
    AvailabilityPortBlock,
    build_port_blocks,
)
from apps.bookings.services.arrivals_pdf.chrome import (
    FOOTER_BAR_H,
    GRID,
    INK,
    MARGIN,
    MUTED,
    NAVY,
    draw_flyer_header,
    draw_table_footer_bar,
    fit_text,
)
from apps.bookings.services.arrivals_pdf.labels import (
    AVAILABILITY_HEADING,
    range_span_label,
)
from apps.bookings.services.arrivals_pdf.logo import port_logo_reader
from apps.bookings.services.arrivals_pdf.overview import (
    ExportOverview,
    draw_overview_band,
)
from apps.bookings.services.arrivals_pdf.occupancy import (
    occupancy_cell_text,
    occupancy_date_label,
    occupancy_weekday,
)

HEADER_H = 2.25 * cm
DATE_W = 2.15 * cm
WKD_W = 1.15 * cm
HEAD_H = 13.0
COUNT_H = 12.0
ROW_H = 13.2


def build_arrivals_availability_pdf(
    bookings: list,
    *,
    ports: list,
    date_from,
    date_to,
    overview: ExportOverview | None = None,
) -> bytes:
    page_w, page_h = landscape(A4)
    updated = timezone.localdate()
    blocks = build_port_blocks(bookings, ports, date_from, date_to)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    kicker = range_span_label(date_from, date_to)

    for block in blocks:
        _draw_port_pages(
            pdf,
            page_w,
            page_h,
            block=block,
            title=AVAILABILITY_HEADING,
            kicker=kicker,
            updated=updated,
            overview=overview,
        )

    pdf.save()
    return buffer.getvalue()


def _draw_port_pages(
    pdf: canvas.Canvas,
    page_w: float,
    page_h: float,
    *,
    block: AvailabilityPortBlock,
    title: str,
    kicker: str,
    updated,
    overview: ExportOverview | None = None,
) -> None:
    logo = port_logo_reader(block.port)
    subtitle = (getattr(block.port, "name", None) or "").strip()
    note = (
        f"{subtitle}  ·  La asignación de posición está sujeta a cambios"
        if subtitle
        else "La asignación de posición está sujeta a cambios"
    )
    x = MARGIN
    table_w = page_w - 2 * MARGIN
    top = page_h - MARGIN - HEADER_H
    if overview is not None:
        top -= 0.95 * cm + 4
    n_pos = max(len(block.labels), 1)
    pos_w = max(1.2 * cm, (table_w - DATE_W - WKD_W) / n_pos)
    col_w = [DATE_W, WKD_W, *([pos_w] * n_pos)]
    body_h = top - HEAD_H - COUNT_H - FOOTER_BAR_H - MARGIN
    max_rows = max(1, int(body_h / ROW_H))
    days = block.days
    chunks = [days[i : i + max_rows] for i in range(0, len(days), max_rows)] or [[]]
    page_count = len(chunks)
    for page_no, chunk in enumerate(chunks, start=1):
        draw_flyer_header(
            pdf,
            page_w,
            page_h,
            logo=logo,
            title=title,
            kicker=kicker,
            subtitle=note,
            title_size=15,
            logo_h=1.2 * cm,
            logo_w=2.4 * cm,
            margin=MARGIN,
        )
        y = page_h - MARGIN - HEADER_H
        y = draw_overview_band(pdf, x, y, table_w, overview)
        y = _draw_header(pdf, x, y, col_w, block.labels, block.counts)
        for day in chunk:
            cells = _day_cells(block.occupied.get(day, []), block.pos_index, n_pos)
            _draw_body_row(
                pdf,
                x,
                y,
                col_w,
                occupancy_date_label(day),
                occupancy_weekday(day),
                cells,
            )
            y -= ROW_H
        draw_table_footer_bar(
            pdf,
            x,
            MARGIN,
            table_w,
            updated=updated,
            kind="calendar",
            page_no=page_no,
            page_count=page_count,
        )
        pdf.showPage()


def _day_cells(bookings: list, pos_index: dict[int, int], n_pos: int) -> list[str]:
    cells = [""] * n_pos
    for booking in sorted(
        bookings,
        key=lambda b: (b.eta or time.min, (b.vessel.name if b.vessel_id else "")),
    ):
        text = occupancy_cell_text(booking)
        idx = pos_index.get(booking.position_id)
        if idx is None:
            idx = n_pos - 1
        cells[idx] = f"{cells[idx]}\n{text}".strip() if cells[idx] else text
    return cells


def _draw_header(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    col_w: list[float],
    labels: list[str],
    counts: list[int],
) -> float:
    headers = ["Fecha", "Día", *labels]
    pdf.setFillColor(NAVY)
    pdf.rect(x, y - HEAD_H, sum(col_w), HEAD_H, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 7)
    cx = x
    for width, label in zip(col_w, headers, strict=True):
        pdf.drawCentredString(cx + width / 2, y - HEAD_H + 4.2, label)
        cx += width
    _stroke(pdf, x, y - HEAD_H, col_w, HEAD_H)
    y -= HEAD_H
    n_pos = len(labels)
    padded = list(counts) + [0] * max(0, n_pos - len(counts))
    count_vals = ["Arribos", "", *[str(n) for n in padded[:n_pos]]]
    pdf.setFillColor(NAVY)
    pdf.rect(x, y - COUNT_H, sum(col_w), COUNT_H, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 7)
    cx = x
    for width, value in zip(col_w, count_vals, strict=True):
        pdf.drawCentredString(cx + width / 2, y - COUNT_H + 3.6, value)
        cx += width
    _stroke(pdf, x, y - COUNT_H, col_w, COUNT_H)
    return y - COUNT_H


def _draw_body_row(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    col_w: list[float],
    date_label: str,
    weekday: str,
    cells: list[str],
) -> None:
    pdf.setFillColor(white)
    pdf.rect(x, y - ROW_H, sum(col_w), ROW_H, fill=1, stroke=0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 6.3)
    pdf.drawString(x + 3, y - ROW_H + ROW_H / 2 - 2, date_label)
    pdf.drawCentredString(x + col_w[0] + col_w[1] / 2, y - ROW_H + ROW_H / 2 - 2, weekday)
    cx = x + col_w[0] + col_w[1]
    for width, value in zip(col_w[2:], cells, strict=True):
        _draw_wrapped_cell(pdf, cx, y, width, value)
        cx += width
    _stroke(pdf, x, y - ROW_H, col_w, ROW_H)


def _draw_wrapped_cell(
    pdf: canvas.Canvas, x: float, y: float, width: float, value: str
) -> None:
    lines = [line for line in value.split("\n") if line][:3]
    if not lines:
        return
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 5.8)
    line_h = 5.4
    total = line_h * len(lines)
    start = y - (ROW_H - total) / 2 - 4.4
    for i, line in enumerate(lines):
        pdf.setFillColor(MUTED if i == 0 and len(lines) > 1 else INK)
        pdf.drawCentredString(
            x + width / 2, start - i * line_h, fit_text(pdf, line, width - 4)
        )


def _stroke(
    pdf: canvas.Canvas, x: float, y: float, col_w: list[float], height: float
) -> None:
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(0.5)
    pdf.rect(x, y, sum(col_w), height, fill=0, stroke=1)
    cx = x
    for width in col_w[:-1]:
        cx += width
        pdf.line(cx, y, cx, y + height)
