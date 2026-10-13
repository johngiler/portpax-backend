"""Year × month matrix reports (port totals, per-port carriers, trends + growth)."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date
from io import BytesIO
from typing import Any

from openpyxl import Workbook

from django.db.models import Q

from apps.bookings.services.report_exports.common import (
    SEASON_NATURAL,
    booking_pax,
    pax_basis_note,
    scheduled_bookings_qs,
    years_in_range,
    PAX_BASIS_PLANNED,
)
from apps.bookings.services.report_exports.season_periods import (
    matrix_periods_for_range,
    normalize_panorama_season,
    period_for_call_date,
)
from apps.bookings.services.report_exports.xlsx_style import (
    ALIGN_LEFT,
    ALIGN_RIGHT,
    BORDER_ALL,
    FONT_DATA,
    FONT_ROW_LABEL,
    FONT_TOTAL,
    FILL_ALT,
    FILL_ROW_LABEL,
    FILL_TOTAL,
    autosize_columns,
    prepare_report_sheet,
    strip_block_outer_border,
    style_cell,
    write_column_header_band,
    write_growth_row,
    write_matrix_header,
    write_matrix_row,
    write_report_banner,
    write_section_banner,
)

from apps.bookings.services.validation.legend_labels import port_legend_label
from apps.catalogs.models import Port, ShippingLine

MONTH_LABELS = (
    "ENE",
    "FEB",
    "MAR",
    "ABR",
    "MAY",
    "JUN",
    "JUL",
    "AGO",
    "SEP",
    "OCT",
    "NOV",
    "DIC",
)

DEFAULT_MATRIX_SECTION_PAGE_SIZE = 2
DEFAULT_TRENDS_LINE_PAGE_SIZE = 10
MAX_REPORT_PAGE_SIZE = 12


def _paginate_items(
    items: list[Any],
    *,
    page: int | None,
    page_size: int | None,
    default_page_size: int,
) -> tuple[list[Any], dict[str, Any]]:
    total_count = len(items)
    if page is None and page_size is None:
        return items, {
            "page": 1,
            "page_size": total_count,
            "total_count": total_count,
            "has_more": False,
        }
    safe_page = max(1, page or 1)
    safe_size = max(
        1, min(page_size or default_page_size, MAX_REPORT_PAGE_SIZE))
    start = (safe_page - 1) * safe_size
    end = start + safe_size
    return items[start:end], {
        "page": safe_page,
        "page_size": safe_size,
        "total_count": total_count,
        "has_more": end < total_count,
    }


def _media_url(request, field) -> str | None:
    if not field:
        return None
    try:
        url = field.url
    except ValueError:
        return None
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def _logo_fs_path(field) -> str | None:
    if not field:
        return None
    try:
        path = field.path
    except Exception:
        return None
    return path if path and os.path.isfile(path) else None


def _logo_storage_name(field) -> str | None:
    if not field:
        return None
    name = getattr(field, "name", None) or ""
    return name or None


def _logo_assets(field, request=None) -> dict[str, str | None]:
    return {
        "url": _media_url(request, field),
        "name": _logo_storage_name(field),
        "path": _logo_fs_path(field),
    }


def _port_logo_assets(
    port_ids: list[int], request=None
) -> dict[int, dict[str, str | None]]:
    if not port_ids:
        return {}
    return {
        port.id: _logo_assets(port.logo, request)
        for port in Port.objects.filter(id__in=port_ids).only("id", "logo")
    }


def _line_logo_assets(
    line_ids: list[int], request=None
) -> dict[int, dict[str, str | None]]:
    if not line_ids:
        return {}
    return {
        line.id: _logo_assets(line.logo, request)
        for line in ShippingLine.objects.filter(id__in=line_ids).only("id", "logo")
    }


def _port_logo_map(port_ids: list[int], request=None) -> dict[int, str | None]:
    return {
        port_id: assets["url"]
        for port_id, assets in _port_logo_assets(port_ids, request).items()
    }


def _line_logo_map(line_ids: list[int], request=None) -> dict[int, str | None]:
    return {
        line_id: assets["url"]
        for line_id, assets in _line_logo_assets(line_ids, request).items()
    }


def _empty_year_months() -> dict[int, dict[int, dict[str, int]]]:
    return defaultdict(lambda: defaultdict(lambda: {"calls": 0, "pax": 0}))


def _port_friendly_name(port: Port | None) -> str:
    """Operator-facing port label — never raw catalog slug/code."""
    label = port_legend_label(port).strip()
    if label:
        return label
    if port is None:
        return "Puerto"
    return (getattr(port, "name", None) or getattr(port, "code", None) or "Puerto").strip()


def _excel_sheet_title(label: str) -> str:
    """Excel sheet name: friendly label, valid chars, max 31."""
    cleaned = (label or "Hoja").strip()
    for ch in r"\/*?:[]":
        cleaned = cleaned.replace(ch, "-")
    cleaned = cleaned.strip() or "Hoja"
    return cleaned[:31]


def _aggregate_by_port(
    qs,
    *,
    pax_basis: str = PAX_BASIS_PLANNED,
) -> tuple[dict[int, dict[int, dict[int, dict[str, int]]]], dict[int, tuple[str, str]]]:
    """port_id -> year -> month -> {calls, pax}."""
    data: dict[int, dict[int, dict[int, dict[str, int]]]
               ] = defaultdict(_empty_year_months)
    meta: dict[int, tuple[str, str]] = {}
    for booking in qs.iterator(chunk_size=500):
        meta[booking.port_id] = (
            booking.port.code,
            _port_friendly_name(booking.port),
        )
        cell = data[booking.port_id][booking.call_date.year][booking.call_date.month]
        cell["calls"] += 1
        cell["pax"] += booking_pax(booking, pax_basis=pax_basis)
    return data, meta


def _aggregate_by_line(
    qs,
    *,
    pax_basis: str = PAX_BASIS_PLANNED,
) -> tuple[dict[int, dict[int, dict[int, dict[str, int]]]], dict[int, tuple[str, str]]]:
    """shipping_line_id -> year -> month -> {calls, pax}."""
    data: dict[int, dict[int, dict[int, dict[str, int]]]
               ] = defaultdict(_empty_year_months)
    meta: dict[int, tuple[str, str]] = {}
    for booking in qs.iterator(chunk_size=500):
        meta[booking.shipping_line_id] = (
            booking.shipping_line.code,
            (booking.shipping_line.name or booking.shipping_line.code or "").strip(),
        )
        cell = data[booking.shipping_line_id][booking.call_date.year][booking.call_date.month]
        cell["calls"] += 1
        cell["pax"] += booking_pax(booking, pax_basis=pax_basis)
    return data, meta


def _aggregate_trends_by_line(
    qs,
    *,
    pax_basis: str = PAX_BASIS_PLANNED,
) -> tuple[
    dict[int, dict[int, dict[str, int]]],
    dict[int, dict[str, Any]],
]:
    """shipping_line_id -> year -> {calls, pax}; meta includes group fields."""
    data: dict[int, dict[int, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"calls": 0, "pax": 0})
    )
    meta: dict[int, dict[str, Any]] = {}
    for booking in qs.iterator(chunk_size=500):
        line = booking.shipping_line
        group = line.group if line is not None else None
        meta[booking.shipping_line_id] = {
            "code": line.code if line else "",
            "name": line.name if line else f"Línea {booking.shipping_line_id}",
            "group_id": group.id if group else 0,
            "group_code": group.code if group else "",
            "group_name": group.name if group else "Sin grupo",
        }
        cell = data[booking.shipping_line_id][booking.call_date.year]
        cell["calls"] += 1
        cell["pax"] += booking_pax(booking, pax_basis=pax_basis)
    return data, meta


def _trend_metrics_for_years(
    year_cells: dict[int, dict[str, int]],
    years: list[int],
) -> dict[str, Any]:
    by_year: list[dict[str, Any]] = []
    total_ships = 0
    total_pax = 0
    for year in years:
        cell = year_cells.get(year, {"calls": 0, "pax": 0})
        ships = int(cell.get("calls", 0) or 0)
        pax = int(cell.get("pax", 0) or 0)
        by_year.append({"year": year, "ships": ships, "pax": pax})
        total_ships += ships
        total_pax += pax

    growth: list[dict[str, Any]] = []
    for idx, year in enumerate(years):
        pax = by_year[idx]["pax"]
        prev = by_year[idx - 1]["pax"] if idx > 0 else 0
        growth.append(
            {
                "year": year,
                "pct": _growth_pct(pax, prev) if idx > 0 else None,
            }
        )
    return {
        "by_year": by_year,
        "growth": growth,
        "total_ships": total_ships,
        "total_pax": total_pax,
    }


def _sum_year_cells(
    items: list[dict[str, Any]],
    years: list[int],
) -> dict[int, dict[str, int]]:
    combined: dict[int, dict[str, int]] = defaultdict(
        lambda: {"calls": 0, "pax": 0}
    )
    for item in items:
        for cell in item.get("by_year") or []:
            year = cell["year"]
            if year not in years:
                continue
            combined[year]["calls"] += int(cell.get("ships", 0) or 0)
            combined[year]["pax"] += int(cell.get("pax", 0) or 0)
    return combined


def _growth_pct(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None if current <= 0 else 100.0
    return round(((current - previous) / previous) * 100)


def build_port_trends(
    *,
    date_from: date,
    date_to: date,
    port_id: int,
    without_lta: bool = False,
    pax_basis: str = PAX_BASIS_PLANNED,
    shipping_line_ids: list[int] | None = None,
    shipping_line_group_ids: list[int] | None = None,
    allowed_ports: set[int] | None = None,
    request=None,
    page: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    port = Port.objects.get(pk=port_id)
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        port_id=port_id,
        shipping_line_ids=shipping_line_ids,
        shipping_line_group_ids=shipping_line_group_ids,
        allowed_ports=allowed_ports,
        without_lta=without_lta,
    )
    line_data, line_meta = _aggregate_trends_by_line(qs, pax_basis=pax_basis)
    years = years_in_range(date_from, date_to)

    line_ids = list(line_data.keys())
    line_logos = _line_logo_map(line_ids, request)

    groups_map: dict[int, dict[str, Any]] = {}
    for line_id in line_ids:
        info = line_meta.get(line_id, {})
        group_id = int(info.get("group_id") or 0)
        metrics = _trend_metrics_for_years(line_data[line_id], years)
        line_row = {
            "shipping_line_id": line_id,
            "code": info.get("code") or "",
            "name": info.get("name") or f"Línea {line_id}",
            "logo": line_logos.get(line_id),
            **metrics,
        }
        if group_id not in groups_map:
            groups_map[group_id] = {
                "shipping_line_group_id": group_id,
                "code": info.get("group_code") or "",
                "name": info.get("group_name") or "Sin grupo",
                "lines": [],
            }
        groups_map[group_id]["lines"].append(line_row)

    groups: list[dict[str, Any]] = []
    for group_id, group in groups_map.items():
        # Highest passenger volume first (ties: name).
        group["lines"].sort(
            key=lambda row: (
                -int(row.get("total_pax") or 0),
                (row.get("name") or "").lower(),
            )
        )
        group_metrics = _trend_metrics_for_years(
            _sum_year_cells(group["lines"], years),
            years,
        )
        groups.append({**group, **group_metrics})
    groups.sort(
        key=lambda row: (
            -int(row.get("total_pax") or 0),
            (row.get("name") or "").lower(),
        )
    )

    totals = _trend_metrics_for_years(_sum_year_cells(groups, years), years)

    page_groups, pagination = _paginate_items(
        groups,
        page=page,
        page_size=page_size,
        default_page_size=DEFAULT_TRENDS_LINE_PAGE_SIZE,
    )
    port_logo = _media_url(request, port.logo)
    port_label = _port_friendly_name(port)
    return {
        "kind": "port_trends",
        "title": f"Trends por puerto — {port_label}",
        "port": {
            "id": port.id,
            "code": port.code,
            "name": port_label,
            "logo": port_logo,
        },
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "without_lta": without_lta,
        "pax_basis": pax_basis,
        "years": years,
        "groups": page_groups,
        "totals": totals,
        "note": (
            f"{pax_basis_note(pax_basis)} Growth % = variación YoY de PAX."
        ),
        **pagination,
    }


def _year_rows_metric(
    agg: dict[Any, dict[int, dict[str, int]]],
    row_axis: list[tuple[Any, Any]],
    metric: str,
    *,
    include_column_totals: bool = True,
) -> list[dict[str, Any]]:
    """Build matrix rows. row_axis = [(agg_key, display_label), ...]."""
    rows: list[dict[str, Any]] = []
    month_totals = [0] * 12
    grand = 0
    for key, label in row_axis:
        months = []
        year_total = 0
        for month in range(1, 13):
            value = agg.get(key, {}).get(month, {}).get(metric, 0)
            months.append(value)
            month_totals[month - 1] += value
            year_total += value
        rows.append({"year": label, "months": months, "total": year_total})
        grand += year_total
    if include_column_totals:
        rows.append(
            {
                "year": "total",
                "months": month_totals,
                "total": grand,
                "is_total": True,
            }
        )
    return rows


def _natural_row_axis(years: list[int]) -> list[tuple[Any, Any]]:
    return [(year, year) for year in years]


def _season_row_axis(periods) -> list[tuple[Any, Any]]:
    return [(period.key, period.label) for period in periods]


def _period_span_label(periods) -> str:
    if not periods:
        return ""
    labels = [p.label for p in periods]
    if len(labels) == 1:
        return labels[0]
    return f"{labels[0]}–{labels[-1]}"


def _empty_keyed_months() -> dict[Any, dict[int, dict[str, int]]]:
    return defaultdict(lambda: defaultdict(lambda: {"calls": 0, "pax": 0}))


def _aggregate_by_port_periods(
    qs,
    periods,
    *,
    pax_basis: str = PAX_BASIS_PLANNED,
) -> tuple[dict[int, dict[Any, dict[int, dict[str, int]]]], dict[int, tuple[str, str]]]:
    """port_id -> period_key -> month -> {calls, pax}."""
    data: dict[int, dict[Any, dict[int, dict[str, int]]]] = defaultdict(
        _empty_keyed_months
    )
    meta: dict[int, tuple[str, str]] = {}
    for booking in qs.iterator(chunk_size=500):
        period = period_for_call_date(booking.call_date, periods)
        if period is None:
            continue
        meta[booking.port_id] = (
            booking.port.code,
            _port_friendly_name(booking.port),
        )
        cell = data[booking.port_id][period.key][booking.call_date.month]
        cell["calls"] += 1
        cell["pax"] += booking_pax(booking, pax_basis=pax_basis)
    return data, meta


def _aggregate_by_line_periods(
    qs,
    periods,
    *,
    pax_basis: str = PAX_BASIS_PLANNED,
) -> tuple[dict[int, dict[Any, dict[int, dict[str, int]]]], dict[int, tuple[str, str]]]:
    """shipping_line_id -> period_key -> month -> {calls, pax}."""
    data: dict[int, dict[Any, dict[int, dict[str, int]]]] = defaultdict(
        _empty_keyed_months
    )
    meta: dict[int, tuple[str, str]] = {}
    for booking in qs.iterator(chunk_size=500):
        period = period_for_call_date(booking.call_date, periods)
        if period is None:
            continue
        meta[booking.shipping_line_id] = (
            booking.shipping_line.code,
            (booking.shipping_line.name or booking.shipping_line.code or "").strip(),
        )
        cell = data[booking.shipping_line_id][period.key][booking.call_date.month]
        cell["calls"] += 1
        cell["pax"] += booking_pax(booking, pax_basis=pax_basis)
    return data, meta


def _combined_line_month_agg(
    line_data: dict[int, dict[Any, dict[int, dict[str, int]]]],
    keys: list[Any],
) -> dict[Any, dict[int, dict[str, int]]]:
    combined: dict[Any, dict[int, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"calls": 0, "pax": 0})
    )
    for line_agg in line_data.values():
        for key in keys:
            for month in range(1, 13):
                cell = line_agg.get(key, {}).get(month, {"calls": 0, "pax": 0})
                combined[key][month]["calls"] += cell["calls"]
                combined[key][month]["pax"] += cell["pax"]
    return combined


def _matrix_section(
    label: str,
    agg: dict[Any, dict[int, dict[str, int]]],
    row_axis: list[tuple[Any, Any]],
    *,
    is_total: bool = False,
    include_column_totals: bool = True,
    logo: str | None = None,
    logo_kind: str | None = None,
    logo_name: str | None = None,
    logo_path: str | None = None,
) -> dict[str, Any]:
    section: dict[str, Any] = {
        "label": label,
        "calls": _year_rows_metric(
            agg, row_axis, "calls", include_column_totals=include_column_totals
        ),
        "pax": _year_rows_metric(
            agg, row_axis, "pax", include_column_totals=include_column_totals
        ),
        "is_total": is_total,
    }
    if logo_kind:
        section["logo_kind"] = logo_kind
    if logo:
        section["logo"] = logo
    if logo_name:
        section["logo_name"] = logo_name
    if logo_path:
        section["logo_path"] = logo_path
    return section


def _scope_allowed_ports(
    allowed_ports: set[int] | None,
    port_ids: set[int] | list[int] | None,
) -> set[int] | None:
    """Intersect user-allowed ports with optional multi-port filter."""
    wanted = {int(pid) for pid in (port_ids or []) if pid}
    if not wanted:
        return allowed_ports
    if allowed_ports is not None:
        return allowed_ports & wanted
    return wanted


def _filter_qs_by_season(qs, *, date_from: date, date_to: date, season: str):
    """Keep bookings whose call_date falls in the season axis periods."""
    axis = normalize_panorama_season(season)
    if axis == SEASON_NATURAL:
        return qs
    periods = matrix_periods_for_range(date_from, date_to, axis)
    if not periods:
        return qs.none()
    date_q = Q()
    for period in periods:
        date_q |= Q(call_date__gte=period.start, call_date__lte=period.end)
    return qs.filter(date_q)


def _port_agg_total_pax(
    port_agg: dict[int, dict[int, dict[str, int]]],
) -> int:
    total = 0
    for year_map in port_agg.values():
        for cell in year_map.values():
            total += int(cell.get("pax", 0) or 0)
    return total


def _line_agg_total_pax(
    line_agg: dict[int, dict[int, dict[str, int]]],
) -> int:
    total = 0
    for month_map in line_agg.values():
        for cell in month_map.values():
            total += int(cell.get("pax", 0) or 0)
    return total


def _resolve_selected_line_ids(
    *,
    shipping_line_ids: list[int] | None,
    shipping_line_group_ids: list[int] | None,
) -> set[int]:
    """Lines win over groups (same rule as Panorama / list filters)."""
    line_ids = {int(lid) for lid in (shipping_line_ids or []) if lid}
    if line_ids:
        return line_ids
    group_ids = {int(gid) for gid in (shipping_line_group_ids or []) if gid}
    if not group_ids:
        return set()
    return set(
        ShippingLine.objects.filter(group_id__in=group_ids).values_list(
            "id", flat=True
        )
    )


def build_ports_totals_matrix(
    *,
    date_from: date,
    date_to: date,
    without_lta: bool = False,
    pax_basis: str = PAX_BASIS_PLANNED,
    allowed_ports: set[int] | None = None,
    port_ids: set[int] | list[int] | None = None,
    season: str = SEASON_NATURAL,
    request=None,
    page: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    season_kind = normalize_panorama_season(season)
    scoped_ports = _scope_allowed_ports(allowed_ports, port_ids)
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        allowed_ports=scoped_ports,
        without_lta=without_lta,
    )
    years = years_in_range(date_from, date_to)
    use_seasons = season_kind != SEASON_NATURAL
    periods = (
        matrix_periods_for_range(date_from, date_to, season_kind)
        if use_seasons
        else []
    )
    if use_seasons:
        qs = _filter_qs_by_season(
            qs, date_from=date_from, date_to=date_to, season=season_kind
        )
        port_data, port_meta = _aggregate_by_port_periods(
            qs, periods, pax_basis=pax_basis
        )
        row_axis = _season_row_axis(periods)
        axis_keys = [key for key, _ in row_axis]
        row_label_header = "Temporada"
    else:
        port_data, port_meta = _aggregate_by_port(qs, pax_basis=pax_basis)
        row_axis = _natural_row_axis(years)
        axis_keys = years
        row_label_header = "Año"

    sections: list[dict[str, Any]] = []
    combined = _combined_line_month_agg(port_data, axis_keys)
    # No vertical TOTAL row (month column sums across years) — keep year TOTAL only.
    sections.append(
        _matrix_section(
            "Total Puertos",
            combined,
            row_axis,
            is_total=True,
            include_column_totals=False,
        ),
    )

    # After grand total: ports by passenger volume (desc), name as tie-breaker.
    sorted_port_ids = sorted(
        port_data.keys(),
        key=lambda pid: (
            -_port_agg_total_pax(port_data[pid]),
            (port_meta.get(pid, ("", ""))[1] or "").lower(),
        ),
    )
    port_logos = _port_logo_assets(sorted_port_ids, request)
    for port_id in sorted_port_ids:
        code, name = port_meta.get(port_id, ("", f"Puerto {port_id}"))
        assets = port_logos.get(port_id) or {}
        sections.append(
            _matrix_section(
                name or code,
                port_data[port_id],
                row_axis,
                include_column_totals=False,
                logo=assets.get("url"),
                logo_name=assets.get("name"),
                logo_path=assets.get("path"),
                logo_kind="port",
            )
        )

    page_sections, pagination = _paginate_items(
        sections,
        page=page,
        page_size=page_size,
        default_page_size=DEFAULT_MATRIX_SECTION_PAGE_SIZE,
    )

    note = pax_basis_note(pax_basis)
    span = _period_span_label(periods) if use_seasons else ""
    if use_seasons and span:
        note = f"{note} Filas: {span}."

    return {
        "kind": "ports_totals",
        "title": "Bookings totals de puertos",
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "without_lta": without_lta,
        "pax_basis": pax_basis,
        "season": season_kind,
        "month_labels": list(MONTH_LABELS),
        "years": years,
        "periods": [p.as_dict() for p in periods] if use_seasons else [],
        "row_label_header": row_label_header,
        "sections": page_sections,
        "note": note,
        **pagination,
    }


def build_port_carrier_matrix(
    *,
    date_from: date,
    date_to: date,
    port_id: int,
    without_lta: bool = False,
    pax_basis: str = PAX_BASIS_PLANNED,
    allowed_ports: set[int] | None = None,
    shipping_line_ids: list[int] | None = None,
    shipping_line_group_ids: list[int] | None = None,
    season: str = SEASON_NATURAL,
    request=None,
    page: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    """
    CALL/PAX matrices per shipping line at one port.

    Columns stay months. Rows are calendar years (natural) or Summer/Winter
    season titles (Temporadas) — same dual-matrix layout either way.
    """
    season_kind = normalize_panorama_season(season)
    port = Port.objects.get(pk=port_id)
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        port_id=port_id,
        allowed_ports=allowed_ports,
        without_lta=without_lta,
    )
    years = years_in_range(date_from, date_to)
    use_seasons = season_kind != SEASON_NATURAL
    periods = (
        matrix_periods_for_range(date_from, date_to, season_kind)
        if use_seasons
        else []
    )
    if use_seasons:
        qs = _filter_qs_by_season(
            qs, date_from=date_from, date_to=date_to, season=season_kind
        )
        line_data, line_meta = _aggregate_by_line_periods(
            qs, periods, pax_basis=pax_basis
        )
        row_axis = _season_row_axis(periods)
        axis_keys = [key for key, _ in row_axis]
        row_label_header = "Temporada"
    else:
        line_data, line_meta = _aggregate_by_line(qs, pax_basis=pax_basis)
        row_axis = _natural_row_axis(years)
        axis_keys = years
        row_label_header = "Año"

    selected_ids = _resolve_selected_line_ids(
        shipping_line_ids=shipping_line_ids,
        shipping_line_group_ids=shipping_line_group_ids,
    )
    has_selection = bool(selected_ids)

    sections: list[dict[str, Any]] = []
    combined = _combined_line_month_agg(line_data, axis_keys) if line_data else {}
    if not combined:
        combined = defaultdict(lambda: defaultdict(lambda: {"calls": 0, "pax": 0}))
    port_assets = _logo_assets(port.logo, request)
    port_label = _port_friendly_name(port)
    sections.append(
        _matrix_section(
            f"Total {port_label}",
            combined,
            row_axis,
            is_total=True,
            logo=port_assets["url"],
            logo_name=port_assets["name"],
            logo_path=port_assets["path"],
            logo_kind="port",
        )
    )

    if has_selection:
        focus_ids = [lid for lid in line_data if lid in selected_ids]
        others_ids = [lid for lid in line_data if lid not in selected_ids]
    else:
        focus_ids = list(line_data.keys())
        others_ids = []

    # Focus lines by passenger volume (desc), name as tie-breaker.
    focus_ids = sorted(
        focus_ids,
        key=lambda lid: (
            -_line_agg_total_pax(line_data[lid]),
            (line_meta.get(lid, ("", ""))[1] or "").lower(),
        ),
    )
    line_logos = _line_logo_assets(focus_ids, request)
    for line_id in focus_ids:
        code, name = line_meta.get(line_id, ("", f"Línea {line_id}"))
        assets = line_logos.get(line_id) or {}
        sections.append(
            _matrix_section(
                name or code,
                line_data[line_id],
                row_axis,
                logo=assets.get("url"),
                logo_name=assets.get("name"),
                logo_path=assets.get("path"),
                logo_kind="shipping_line",
            )
        )

    if has_selection and others_ids:
        others_data = {lid: line_data[lid] for lid in others_ids}
        others_combined = _combined_line_month_agg(others_data, axis_keys)
        sections.append(
            _matrix_section(
                "Otros",
                others_combined,
                row_axis,
                logo_kind="shipping_line",
            )
        )

    page_sections, pagination = _paginate_items(
        sections,
        page=page,
        page_size=page_size,
        default_page_size=DEFAULT_MATRIX_SECTION_PAGE_SIZE,
    )

    note = pax_basis_note(pax_basis)
    span = _period_span_label(periods) if use_seasons else ""
    if use_seasons and span:
        note = f"{note} Filas: {span}."

    return {
        "kind": "port_carrier",
        "title": f"Bookings totals por puerto — {port_label}",
        "port": {
            "id": port.id,
            "code": port.code,
            "name": port_label,
            "logo": port_assets["url"],
        },
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "without_lta": without_lta,
        "pax_basis": pax_basis,
        "season": season_kind,
        "month_labels": list(MONTH_LABELS),
        "years": years,
        "periods": [p.as_dict() for p in periods] if use_seasons else [],
        "row_label_header": row_label_header,
        "sections": page_sections,
        "note": note,
        **pagination,
    }


def _matrix_subtitle(report: dict[str, Any]) -> str:
    parts: list[str] = []
    date_from = report.get("date_from") or ""
    date_to = report.get("date_to") or ""
    if date_from and date_to:
        parts.append(f"{date_from} → {date_to}")
    note = report.get("note") or ""
    if report.get("without_lta"):
        note = f"{note} Sin LTA.".strip() if note else "Sin LTA."
    if note:
        parts.append(note)
    return " · ".join(parts)


def _write_matrix_block(
    ws,
    start_row: int,
    *,
    title: str,
    subtitle: str | None,
    sections: list[dict[str, Any]],
    metric_key: str,
    row_label_header: str,
) -> int:
    col_span = 14
    row = write_report_banner(
        ws,
        start_row,
        title=title,
        subtitle=subtitle,
        col_span=col_span,
    )
    for section in sections:
        write_section_banner(ws, row, section["label"], col_span)
        row += 1
        write_matrix_header(
            ws, row, row_label=row_label_header, month_labels=MONTH_LABELS)
        block_start = row
        row += 1
        rows = section[metric_key]
        for idx, data_row in enumerate(rows):
            label = str(data_row["year"]
                        ) if data_row["year"] != "total" else "TOTAL"
            write_matrix_row(
                ws,
                row,
                label=label,
                values=data_row["months"] + [data_row["total"]],
                is_total=data_row.get("is_total", False),
                alt=idx % 2 == 1 and not data_row.get("is_total"),
            )
            row += 1
        if row > block_start + 1:
            strip_block_outer_border(
                ws,
                min_row=block_start,
                max_row=row - 1,
                min_col=1,
                max_col=col_span,
            )
        row += 1
    return row


def _write_dual_matrix_sheet(
    wb: Workbook,
    *,
    sheet_title: str,
    report: dict[str, Any],
    calls_title: str,
    pax_title: str,
) -> None:
    ws = wb.active if wb.sheetnames == [
        "Sheet"] else wb.create_sheet(sheet_title)
    ws.title = sheet_title[:31]
    if wb.sheetnames[0] == "Sheet" and ws.title != "Sheet":
        wb.remove(wb["Sheet"])

    prepare_report_sheet(ws)
    subtitle = _matrix_subtitle(report)
    row_header = str(report.get("row_label_header") or "Año").upper()
    end_calls = _write_matrix_block(
        ws,
        1,
        title=calls_title,
        subtitle=subtitle or None,
        sections=report["sections"],
        metric_key="calls",
        row_label_header=row_header,
    )
    _write_matrix_block(
        ws,
        end_calls + 1,
        title=pax_title,
        subtitle=subtitle or None,
        sections=report["sections"],
        metric_key="pax",
        row_label_header=row_header,
    )
    autosize_columns(ws)


def build_ports_totals_matrix_xlsx(**kwargs) -> bytes:
    report = build_ports_totals_matrix(**kwargs)
    wb = Workbook()
    _write_dual_matrix_sheet(
        wb,
        sheet_title="Totals Puertos",
        report=report,
        calls_title="CALL SUMMARY ITM PORTS",
        pax_title="PASSENGER SUMMARY ITM PORTS",
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_port_carrier_matrix_xlsx(**kwargs) -> bytes:
    report = build_port_carrier_matrix(**kwargs)
    port_name = report["port"]["name"]
    wb = Workbook()
    _write_dual_matrix_sheet(
        wb,
        sheet_title=_excel_sheet_title(port_name),
        report=report,
        calls_title=f"CALL SUMMARY {port_name.upper()}",
        pax_title=f"PASSENGER SUMMARY {port_name.upper()}",
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_port_trends_xlsx(**kwargs) -> bytes:
    report = build_port_trends(**kwargs)
    years = report["years"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Trends"
    prepare_report_sheet(ws)
    port_name = report["port"]["name"]
    subtitle = _matrix_subtitle(report)

    header = ["Grupo / Naviera"]
    for year in years:
        header.extend([f"{year} SHIPS", f"{year} PAX"])
    header.extend(["Total SHIPS", "Total PAX"])
    trends_cols = len(header)

    row = write_report_banner(
        ws,
        1,
        title=f"TRENDS — {port_name.upper()}",
        subtitle=subtitle or None,
        col_span=trends_cols,
    )
    header_row = row
    write_column_header_band(ws, row, header)
    row += 1
    body_start = row

    def write_metric_row(
        *,
        label: str,
        item: dict[str, Any],
        idx: int,
        is_group: bool = False,
        is_total: bool = False,
    ) -> None:
        nonlocal row
        values: list[Any] = [label]
        for cell in item["by_year"]:
            values.extend([cell["ships"] or "", cell["pax"] or ""])
        values.extend([item["total_ships"] or "", item["total_pax"] or ""])
        emphasize = is_group or is_total
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col,
                           value=value if value != 0 else "")
            if emphasize:
                font = FONT_TOTAL
                fill = FILL_TOTAL
            elif col == 1:
                font = FONT_ROW_LABEL
                fill = FILL_ROW_LABEL
            else:
                font = FONT_DATA
                fill = FILL_ALT if idx % 2 else None
            style_cell(
                cell,
                font=font,
                fill=fill,
                alignment=ALIGN_LEFT if col == 1 else ALIGN_RIGHT,
                border=BORDER_ALL,
                number_format="#,##0" if isinstance(
                    value, int) and col > 1 else None,
            )
        row += 1

    for g_idx, group in enumerate(report.get("groups") or []):
        write_metric_row(
            label=group["name"],
            item=group,
            idx=g_idx,
            is_group=True,
        )
        for l_idx, line in enumerate(group.get("lines") or []):
            write_metric_row(
                label=f"  {line['name']}",
                item=line,
                idx=g_idx + l_idx + 1,
            )

    totals = report.get("totals")
    if totals:
        write_metric_row(label="TOTAL", item=totals, idx=0, is_total=True)

    body_end = row - 1
    if body_end >= body_start:
        strip_block_outer_border(
            ws,
            min_row=header_row,
            max_row=body_end,
            min_col=1,
            max_col=trends_cols,
        )
    autosize_columns(ws)

    # Own sheet so Growth banner width matches its body (no empty cols from Trends).
    ws_g = wb.create_sheet("Growth")
    prepare_report_sheet(ws_g)
    growth_cols = 1 + len(years)
    grow = write_report_banner(
        ws_g,
        1,
        title="GROWTH PERCENTAGE (PAX YoY)",
        subtitle=subtitle or None,
        col_span=growth_cols,
    )
    g_header_row = grow
    write_column_header_band(
        ws_g, grow, ["Grupo / Naviera", *[str(y) for y in years]]
    )
    grow += 1
    g_body_start = grow

    for group in report.get("groups") or []:
        write_growth_row(
            ws_g,
            grow,
            label=group["name"],
            values=[g["pct"] for g in group["growth"]],
            is_group=True,
        )
        grow += 1
        for line in group.get("lines") or []:
            write_growth_row(
                ws_g,
                grow,
                label=f"  {line['name']}",
                values=[g["pct"] for g in line["growth"]],
            )
            grow += 1

    if totals:
        write_growth_row(
            ws_g,
            grow,
            label="TOTAL",
            values=[g["pct"] for g in totals["growth"]],
            is_total=True,
        )
        grow += 1

    g_body_end = grow - 1
    if g_body_end >= g_body_start:
        strip_block_outer_border(
            ws_g,
            min_row=g_header_row,
            max_row=g_body_end,
            min_col=1,
            max_col=growth_cols,
        )
    autosize_columns(ws_g)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ports_totals_matrix_filename(
    date_from: date,
    date_to: date,
    ext: str = "xlsx",
) -> str:
    _ = (date_from, date_to)
    from apps.bookings.services.report_exports.filenames import report_download_filename

    return report_download_filename("ports_totals_matrix", ext)


def port_carrier_matrix_filename(
    port_code: str,
    date_from: date,
    date_to: date,
    ext: str = "xlsx",
) -> str:
    _ = (port_code, date_from, date_to)
    from apps.bookings.services.report_exports.filenames import report_download_filename

    return report_download_filename("port_carrier_matrix", ext)


def port_trends_filename(
    port_code: str,
    date_from: date,
    date_to: date,
    ext: str = "xlsx",
) -> str:
    _ = (port_code, date_from, date_to)
    from apps.bookings.services.report_exports.filenames import report_download_filename

    return report_download_filename("port_trends", ext)
