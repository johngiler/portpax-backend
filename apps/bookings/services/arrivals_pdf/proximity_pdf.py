"""Landscape proximity flyer — call dates × ports for one vessel."""

from __future__ import annotations

from datetime import date
from io import BytesIO

from django.utils import timezone
from reportlab.lib.colors import HexColor, white
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
    draw_logo,
    draw_table_footer_bar,
    fit_text,
)
from apps.bookings.services.arrivals_pdf.labels import format_hhmm, list_date_label
from apps.bookings.services.arrivals_pdf.logo import port_logo_reader
from apps.bookings.services.arrivals_pdf.overview import (
    ExportOverview,
    draw_overview_band,
)

DATE_W = 2.6 * cm
HEAD_H = 16.0
ROW_H = 22.0
SAME_DAY = HexColor("#DBEAFE")
PROX = HexColor("#FEF3C7")
PORTS_PER_PAGE = 6


def build_proximity_matrix_pdf(
    payload: dict, *, overview: ExportOverview | None = None
) -> bytes:
    vessel = str(payload.get("vessel_name") or "Barco")
    line = str(payload.get("shipping_line_name") or "").strip()
    subtitle = line
    ports = list(payload.get("ports") or []) or [{"id": 0, "name": "—"}]
    dates = list(payload.get("dates") or [])
    cells = list(payload.get("cells") or [])
    by_key = {
        (str(cell.get("date") or ""), int(cell.get("port_id") or 0)): cell
        for cell in cells
    }

    page_w, page_h = landscape(A4)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    updated = timezone.localdate()
    readers = _port_logo_readers(ports)
    header_logo = readers[0] if len(ports) == 1 else None
    port_groups = [
        list(range(i, min(i + PORTS_PER_PAGE, len(ports))))
        for i in range(0, len(ports), PORTS_PER_PAGE)
    ] or [[]]
    table_top = page_h - MARGIN - HEADER_H
    if overview is not None:
        table_top -= 0.95 * cm + 4
    body_h = table_top - 28.0 - FOOTER_BAR_H - MARGIN
    max_rows = max(1, int(body_h / ROW_H))
    pages: list[tuple[list[int], list[str]]] = []
    for group in port_groups:
        group_ids = {int(ports[i].get("id") or 0) for i in group}
        group_dates = [
            iso
            for iso in dates
            if any(by_key.get((iso, pid)) for pid in group_ids)
        ]
        if not group_dates:
            continue
        for i in range(0, len(group_dates), max_rows):
            pages.append((group, group_dates[i : i + max_rows]))
    if not pages:
        pages = [(port_groups[0], [])]
    page_count = len(pages)

    for page_no, (group, chunk) in enumerate(pages, start=1):
        group_ports = [ports[i] for i in group]
        group_readers = [readers[i] for i in group]
        labels = [str(port.get("name") or "") for port in group_ports]
        n_pos = max(len(labels), 1)
        table_w = page_w - 2 * MARGIN
        pos_w = (table_w - DATE_W) / n_pos
        col_w = [DATE_W, *([pos_w] * n_pos)]
        head_h = 28.0 if any(group_readers) else HEAD_H
        draw_flyer_header(
            pdf,
            page_w,
            page_h,
            logo=header_logo,
            title=f"Proximidad · {vessel}",
            subtitle=subtitle,
            total=len(cells) if page_no == 1 else None,
            title_size=16,
            logo_h=1.2 * cm,
            margin=MARGIN,
        )
        x = MARGIN
        y = page_h - MARGIN - HEADER_H
        y = draw_overview_band(pdf, x, y, table_w, overview)
        y = _draw_header_row(pdf, x, y, col_w, labels, group_readers, head_h)
        for iso in chunk:
            row_cells = [
                by_key.get((iso, int(port.get("id") or 0))) for port in group_ports
            ]
            _draw_body_row(pdf, x, y, col_w, _date_label(iso), row_cells)
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

    pdf.save()
    return buffer.getvalue()


def _port_logo_readers(ports: list[dict]):
    ids = [int(port.get("id") or 0) for port in ports if port.get("id")]
    if not ids:
        return [None] * len(ports)
    from apps.catalogs.models import Port

    found = {item.id: item for item in Port.objects.filter(id__in=ids)}
    return [port_logo_reader(found.get(int(port.get("id") or 0))) for port in ports]


def _date_label(iso: str) -> str:
    try:
        return list_date_label(date.fromisoformat(iso))
    except ValueError:
        return iso


def _draw_header_row(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    col_w: list[float],
    labels: list[str],
    readers: list,
    height: float,
) -> float:
    pdf.setFillColor(NAVY)
    pdf.rect(x, y - height, sum(col_w), height, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 7.2)
    headers = ["Fecha", *labels]
    logos = [None, *readers]
    cx = x
    for width, label, reader in zip(col_w, headers, logos, strict=True):
        if reader is not None:
            draw_logo(
                pdf,
                reader,
                cx + 4,
                y - height + 12,
                max_w=width - 8,
                max_h=height - 16,
            )
            pdf.setFillColor(white)
            pdf.setFont("Helvetica-Bold", 6.4)
            pdf.drawCentredString(
                cx + width / 2, y - height + 3.5, fit_text(pdf, label, width - 6)
            )
        else:
            pdf.setFillColor(white)
            pdf.setFont("Helvetica-Bold", 7.2)
            pdf.drawCentredString(
                cx + width / 2, y - height + 5, fit_text(pdf, label, width - 6)
            )
        cx += width
    _stroke(pdf, x, y - height, col_w, height)
    return y - height


def _draw_body_row(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    col_w: list[float],
    date_label: str,
    cells: list[dict | None],
) -> None:
    pdf.setFillColor(white)
    pdf.rect(x, y - ROW_H, col_w[0], ROW_H, fill=1, stroke=0)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(x + 4, y - ROW_H + ROW_H / 2 - 2.4, date_label)
    cx = x + col_w[0]
    for width, cell in zip(col_w[1:], cells, strict=True):
        fill = white
        if cell:
            status = str(cell.get("cell_status") or "")
            if status == "same_day":
                fill = SAME_DAY
            elif status == "proximity":
                fill = PROX
        pdf.setFillColor(fill)
        pdf.rect(cx, y - ROW_H, width, ROW_H, fill=1, stroke=0)
        if cell:
            _draw_cell_text(pdf, cx, y, width, cell)
        cx += width
    _stroke(pdf, x, y - ROW_H, col_w, ROW_H)


def _draw_cell_text(
    pdf: canvas.Canvas, x: float, y: float, width: float, cell: dict
) -> None:
    position = str(cell.get("position_code") or "").strip() or "—"
    eta = _iso_time(cell.get("eta"))
    etd = _iso_time(cell.get("etd"))
    times = "–".join(part for part in (eta, etd) if part)
    mark = ""
    status = str(cell.get("cell_status") or "")
    if status == "same_day":
        mark = "mismo día"
    elif status == "proximity":
        mark = "prox."
    if cell.get("first_arrival"):
        mark = f"{mark} · 1er arribo".strip(" ·")
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 6.4)
    pdf.drawCentredString(x + width / 2, y - 8.2, fit_text(pdf, position, width - 6))
    pdf.setFont("Helvetica", 6.1)
    if times:
        pdf.drawCentredString(x + width / 2, y - 15.2, times)
    if mark:
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 5.6)
        pdf.drawCentredString(x + width / 2, y - 21.2, fit_text(pdf, mark, width - 6))


def _iso_time(value) -> str:
    if not value:
        return ""
    text = str(value)
    if len(text) >= 5 and text[2] == ":":
        return text[:5]
    try:
        from datetime import time as time_cls

        parsed = time_cls.fromisoformat(text)
        return format_hhmm(parsed)
    except ValueError:
        return text


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
