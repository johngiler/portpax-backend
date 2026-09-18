"""Shared openpyxl styling for ITM-style operational report exports."""

from __future__ import annotations

from typing import Any

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from apps.bookings.services.report_exports.report_theme import (
    BODY_SIZE,
    FONT_FAMILY_XLSX,
    GRID,
    GROWTH_NEG,
    GROWTH_POS,
    HEADER_SIZE,
    MUTED,
    NAVY,
    NAVY_MID,
    NOTE_SIZE,
    SECTION_SIZE,
    SKY,
    SKY_LIGHT,
    SUBTITLE_SIZE,
    TEXT,
    TITLE_SIZE,
    WHITE,
)

_THIN = Side(style="thin", color=GRID)
# Interior separators only (right+bottom). Outer perimeter is stripped per block.
BORDER_GRID = Border(right=_THIN, bottom=_THIN)
BORDER_ALL = BORDER_GRID
BORDER_NONE = Border(
    left=Side(style=None),
    right=Side(style=None),
    top=Side(style=None),
    bottom=Side(style=None),
)

FONT_TITLE = Font(
    name=FONT_FAMILY_XLSX, size=TITLE_SIZE, bold=True, color=NAVY
)
FONT_SUBTITLE = Font(
    name=FONT_FAMILY_XLSX, size=SUBTITLE_SIZE, bold=True, color=NAVY_MID
)
FONT_SECTION = Font(
    name=FONT_FAMILY_XLSX, size=SECTION_SIZE, bold=True, color=WHITE
)
FONT_HEADER = Font(
    name=FONT_FAMILY_XLSX, size=HEADER_SIZE, bold=True, color=WHITE
)
FONT_ROW_LABEL = Font(
    name=FONT_FAMILY_XLSX, size=BODY_SIZE, bold=True, color=NAVY
)
FONT_DATA = Font(name=FONT_FAMILY_XLSX, size=BODY_SIZE, color=TEXT)
FONT_TOTAL = Font(
    name=FONT_FAMILY_XLSX, size=BODY_SIZE, bold=True, color=NAVY
)
FONT_GROWTH_POS = Font(
    name=FONT_FAMILY_XLSX, size=BODY_SIZE, bold=True, color=GROWTH_POS
)
FONT_GROWTH_NEG = Font(
    name=FONT_FAMILY_XLSX, size=BODY_SIZE, bold=True, color=GROWTH_NEG
)
FONT_NOTE = Font(
    name=FONT_FAMILY_XLSX, size=NOTE_SIZE, italic=True, color=MUTED
)

FILL_TITLE = PatternFill("solid", fgColor=SKY_LIGHT)
FILL_SECTION = PatternFill("solid", fgColor=NAVY_MID)
FILL_HEADER = PatternFill("solid", fgColor=NAVY)
FILL_ROW_LABEL = PatternFill("solid", fgColor=SKY)
FILL_TOTAL = PatternFill("solid", fgColor=SKY_LIGHT)
FILL_ALT = PatternFill("solid", fgColor=WHITE)
# Weekly Sem. badge (matches HTML WeekBadge / PDF peach card).
FILL_WEEK_BADGE = PatternFill("solid", fgColor="FCE4D6")

ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
ALIGN_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")
ALIGN_LEFT_NO_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=False)


def style_cell(
    cell,
    *,
    font: Font | None = None,
    fill: PatternFill | None = None,
    alignment: Alignment | None = None,
    border: Border | None = BORDER_NONE,
    number_format: str | None = None,
) -> None:
    if font is not None:
        cell.font = font
    if fill is not None:
        cell.fill = fill
    if alignment is not None:
        cell.alignment = alignment
    if border is not None:
        cell.border = border
    if number_format is not None:
        cell.number_format = number_format


def prepare_report_sheet(ws: Worksheet) -> None:
    """Hide Excel gridlines so empty cells do not look bordered."""
    ws.sheet_view.showGridLines = False


def clear_range_borders(
    ws: Worksheet,
    *,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
) -> None:
    """Force no borders on a rectangle (banner / column header)."""
    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            ws.cell(row=row, column=col).border = BORDER_NONE


def strip_block_outer_border(
    ws: Worksheet,
    *,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
) -> None:
    """
    Keep subtle interior grid; remove the closed outer frame of the block.

    That outer frame is what reads as the “black line” around Trends/Growth.
    """
    if max_row < min_row or max_col < min_col:
        return
    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row, column=col)
            existing = cell.border or BORDER_NONE
            cell.border = Border(
                left=None if col == min_col else existing.left,
                right=None if col == max_col else existing.right,
                top=None if row == min_row else existing.top,
                bottom=None if row == max_row else existing.bottom,
            )


def _paint_merged_band(
    ws: Worksheet,
    row: int,
    col_span: int,
    *,
    value: str,
    font: Font,
    fill: PatternFill,
    alignment: Alignment = ALIGN_LEFT,
) -> None:
    """Merge one row across ``col_span`` and paint fill on every cell in the span."""
    if col_span < 1:
        col_span = 1
    # Paint fill first, then merge — Excel keeps top-left style for the merged area.
    for col in range(1, col_span + 1):
        cell = ws.cell(row=row, column=col)
        if col == 1:
            cell.value = value
        else:
            cell.value = None
        style_cell(cell, font=font, fill=fill, alignment=alignment, border=BORDER_NONE)
    if col_span > 1:
        ws.merge_cells(
            start_row=row, start_column=1, end_row=row, end_column=col_span
        )
    clear_range_borders(
        ws, min_row=row, max_row=row, min_col=1, max_col=col_span
    )


def _banner_row_height(text: str, col_span: int, *, base: float = 18) -> float:
    """Rough height so wrapped banner text stays inside the band."""
    chars_per_line = max(24, col_span * 10)
    lines = max(1, (len(text) + chars_per_line - 1) // chars_per_line)
    return min(60.0, base * lines)


def write_report_banner(
    ws: Worksheet,
    start_row: int,
    *,
    title: str,
    subtitle: str | None = None,
    col_span: int,
    right_badge: str | None = None,
) -> int:
    """
    Unified header band spanning exactly ``col_span`` columns (full table width).
    Title + optional subtitle are contiguous filled rows — no blank spacer below.
    Optional ``right_badge`` (e.g. Sem. card) sits in the last column of the banner.
    Returns the next free row immediately after the banner.
    """
    prepare_report_sheet(ws)
    badge = (right_badge or "").strip() or None
    use_badge = bool(badge) and col_span >= 2
    title_span = col_span - 1 if use_badge else col_span

    _paint_merged_band(
        ws,
        start_row,
        title_span,
        value=title,
        font=FONT_TITLE,
        fill=FILL_TITLE,
    )
    ws.row_dimensions[start_row].height = _banner_row_height(
        title, title_span, base=22
    )
    next_row = start_row + 1
    if subtitle and str(subtitle).strip():
        sub = str(subtitle).strip()
        _paint_merged_band(
            ws,
            next_row,
            title_span,
            value=sub,
            font=FONT_SUBTITLE,
            fill=FILL_TITLE,
        )
        ws.row_dimensions[next_row].height = _banner_row_height(
            sub, title_span, base=18
        )
        next_row += 1

    if use_badge:
        badge_top = start_row
        badge_bottom = next_row - 1
        for r in range(badge_top, badge_bottom + 1):
            cell = ws.cell(row=r, column=col_span)
            if r == badge_top:
                cell.value = badge
            else:
                cell.value = None
            style_cell(
                cell,
                font=Font(
                    name=FONT_FAMILY_XLSX,
                    size=SUBTITLE_SIZE,
                    bold=True,
                    color=TEXT,
                ),
                fill=FILL_WEEK_BADGE,
                alignment=Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                ),
                border=BORDER_NONE,
            )
        if badge_bottom > badge_top:
            ws.merge_cells(
                start_row=badge_top,
                start_column=col_span,
                end_row=badge_bottom,
                end_column=col_span,
            )
        clear_range_borders(
            ws,
            min_row=badge_top,
            max_row=badge_bottom,
            min_col=col_span,
            max_col=col_span,
        )

    return next_row


def write_title_row(ws: Worksheet, row: int, title: str, col_span: int) -> None:
    """Backward-compatible alias: title-only banner (no subtitle)."""
    write_report_banner(ws, row, title=title, col_span=col_span)


def write_section_banner(ws: Worksheet, row: int, label: str, col_span: int) -> None:
    _paint_merged_band(
        ws,
        row,
        col_span,
        value=label,
        font=FONT_SECTION,
        fill=FILL_SECTION,
    )


def write_column_header_band(
    ws: Worksheet,
    row: int,
    labels: list[str],
) -> None:
    """Column headers as one visual band (same fill; wrap if labels are long)."""
    for col, text in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=col, value=text)
        style_cell(
            cell,
            font=FONT_HEADER,
            fill=FILL_HEADER,
            alignment=ALIGN_LEFT if col == 1 else ALIGN_CENTER,
            border=BORDER_NONE,
        )
    clear_range_borders(
        ws, min_row=row, max_row=row, min_col=1, max_col=max(len(labels), 1)
    )
    # Allow wrap for long year/metric labels without clipping.
    longest = max((len(str(t)) for t in labels), default=0)
    ws.row_dimensions[row].height = 28 if longest > 12 else 20


def write_matrix_header(
    ws: Worksheet,
    row: int,
    *,
    row_label: str,
    month_labels: tuple[str, ...],
    total_label: str = "TOTAL",
) -> None:
    write_column_header_band(
        ws,
        row,
        [row_label, *month_labels, total_label],
    )


def write_matrix_row(
    ws: Worksheet,
    row: int,
    *,
    label: str,
    values: list[int | float | None],
    is_total: bool = False,
    alt: bool = False,
) -> None:
    label_font = FONT_TOTAL if is_total else FONT_ROW_LABEL
    label_fill = FILL_TOTAL if is_total else (FILL_ALT if alt else FILL_ROW_LABEL)
    data_font = FONT_TOTAL if is_total else FONT_DATA
    data_fill = FILL_TOTAL if is_total else (FILL_ALT if alt else None)

    label_cell = ws.cell(row=row, column=1, value=label)
    style_cell(
        label_cell,
        font=label_font,
        fill=label_fill,
        alignment=ALIGN_LEFT,
        border=BORDER_ALL,
    )

    for idx, value in enumerate(values, start=2):
        cell = ws.cell(row=row, column=idx, value=value if value else "")
        fmt = "#,##0" if isinstance(value, (int, float)) and value else None
        style_cell(
            cell,
            font=data_font,
            fill=data_fill,
            alignment=ALIGN_RIGHT,
            border=BORDER_ALL,
            number_format=fmt,
        )


def write_growth_row(
    ws: Worksheet,
    row: int,
    *,
    label: str,
    values: list[float | None],
    is_group: bool = False,
    is_total: bool = False,
) -> None:
    emphasize = is_group or is_total
    label_font = FONT_TOTAL if emphasize else FONT_ROW_LABEL
    label_fill = FILL_TOTAL if emphasize else FILL_ROW_LABEL
    row_fill = FILL_TOTAL if emphasize else None
    label_cell = ws.cell(row=row, column=1, value=label)
    style_cell(
        label_cell,
        font=label_font,
        fill=label_fill,
        alignment=ALIGN_LEFT,
        border=BORDER_ALL,
    )
    for idx, value in enumerate(values, start=2):
        cell = ws.cell(row=row, column=idx)
        if value is None:
            cell.value = ""
            style_cell(
                cell,
                font=FONT_DATA,
                fill=row_fill,
                alignment=ALIGN_RIGHT,
                border=BORDER_GRID,
            )
            continue
        cell.value = value / 100.0
        font = (
            FONT_GROWTH_POS
            if value > 0
            else FONT_GROWTH_NEG
            if value < 0
            else (FONT_TOTAL if emphasize else FONT_DATA)
        )
        style_cell(
            cell,
            font=font,
            fill=row_fill,
            alignment=ALIGN_RIGHT,
            border=BORDER_ALL,
            number_format="0%",
        )


def write_flat_data_rows(
    ws: Worksheet,
    start_row: int,
    rows: list[list[Any]],
    *,
    col_count: int,
) -> int:
    """Write body rows with alternating fill + subtle cell borders."""
    row = start_row
    for idx, values in enumerate(rows):
        fill = FILL_ALT if idx % 2 else None
        for col in range(1, col_count + 1):
            value = values[col - 1] if col - 1 < len(values) else ""
            cell = ws.cell(row=row, column=col, value=value if value != "" else "")
            style_cell(
                cell,
                font=FONT_DATA,
                fill=fill,
                alignment=ALIGN_LEFT if col == 1 else ALIGN_CENTER,
                border=BORDER_GRID,
            )
        row += 1
    return row


def write_report_table_block(
    ws: Worksheet,
    start_row: int,
    *,
    title: str,
    subtitle: str | None,
    headers: list[str],
    rows: list[list[Any]],
) -> int:
    """
    Standard report block: banner → column header band → data (no parent outline).
    Returns the next free row after the block.
    """
    col_span = max(len(headers), 1)
    row = write_report_banner(
        ws, start_row, title=title, subtitle=subtitle, col_span=col_span
    )
    write_column_header_band(ws, row, headers)
    row += 1
    body_start = row
    row = write_flat_data_rows(ws, row, rows, col_count=col_span)
    if row > body_start:
        strip_block_outer_border(
            ws,
            min_row=body_start - 1,  # include header band
            max_row=row - 1,
            min_col=1,
            max_col=col_span,
        )
    return row + 1


def autosize_columns(ws: Worksheet, min_width: int = 8, max_width: int = 18) -> None:
    for col_idx in range(1, (ws.max_column or 1) + 1):
        letter = get_column_letter(col_idx)
        max_len = min_width
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value is not None and str(cell.value).strip() != "":
                    max_len = max(max_len, min(len(str(cell.value)) + 2, max_width))
        ws.column_dimensions[letter].width = max_len
