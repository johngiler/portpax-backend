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
# Cruise year (Summer + Winter): May → April.
CRUISE_YEAR_MONTHS = (5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4)
CRUISE_YEAR_MONTH_LABELS = tuple(MONTH_LABELS[month - 1] for month in CRUISE_YEAR_MONTHS)
CALENDAR_MONTHS = tuple(range(1, 13))

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


def _trends_line_meta_from_booking(booking) -> dict[str, Any]:
    line = booking.shipping_line
    group = line.group if line is not None else None
    return {
        "code": line.code if line else "",
        "name": line.name if line else f"Línea {booking.shipping_line_id}",
        "group_id": group.id if group else 0,
        "group_code": group.code if group else "",
        "group_name": group.name if group else "Sin grupo",
    }


def _aggregate_trends_by_line(
    qs,
    *,
    pax_basis: str = PAX_BASIS_PLANNED,
) -> tuple[
    dict[int, dict[Any, dict[str, int]]],
    dict[int, dict[str, Any]],
]:
    """shipping_line_id -> year -> {calls, pax}; meta includes group fields."""
    data: dict[int, dict[Any, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"calls": 0, "pax": 0})
    )
    meta: dict[int, dict[str, Any]] = {}
    for booking in qs.iterator(chunk_size=500):
        meta[booking.shipping_line_id] = _trends_line_meta_from_booking(booking)
        cell = data[booking.shipping_line_id][booking.call_date.year]
        cell["calls"] += 1
        cell["pax"] += booking_pax(booking, pax_basis=pax_basis)
    return data, meta


def _aggregate_trends_by_line_periods(
    qs,
    periods,
    *,
    pax_basis: str = PAX_BASIS_PLANNED,
) -> tuple[
    dict[int, dict[Any, dict[str, int]]],
    dict[int, dict[str, Any]],
]:
    """shipping_line_id -> period_key -> {calls, pax}."""
    data: dict[int, dict[Any, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"calls": 0, "pax": 0})
    )
    meta: dict[int, dict[str, Any]] = {}
    for booking in qs.iterator(chunk_size=500):
        period = period_for_call_date(booking.call_date, periods)
        if period is None:
            continue
        meta[booking.shipping_line_id] = _trends_line_meta_from_booking(booking)
        cell = data[booking.shipping_line_id][period.key]
        cell["calls"] += 1
        cell["pax"] += booking_pax(booking, pax_basis=pax_basis)
    return data, meta


def _axis_growth_prev_indices(
    row_axis: list[tuple[Any, Any]],
    periods,
) -> list[int | None]:
    """Natural years: YoY. Temporadas: Summer vs prior Summer, Winter vs prior Winter."""
    if not periods:
        return [None if idx == 0 else idx - 1 for idx in range(len(row_axis))]
    by_key = {period.key: period for period in periods}
    last_of_kind: dict[str, int] = {}
    out: list[int | None] = []
    for idx, (key, _label) in enumerate(row_axis):
        period = by_key.get(key)
        kind = period.kind if period is not None else None
        if kind:
            out.append(last_of_kind.get(kind))
            last_of_kind[kind] = idx
        else:
            out.append(None if idx == 0 else idx - 1)
    return out


def _trend_metrics_for_axis(
    axis_cells: dict[Any, dict[str, int]],
    row_axis: list[tuple[Any, Any]],
    *,
    prev_indices: list[int | None] | None = None,
) -> dict[str, Any]:
    """Build Ships/PAX + growth along natural years or season periods."""
    by_year: list[dict[str, Any]] = []
    total_ships = 0
    total_pax = 0
    for key, label in row_axis:
        cell = axis_cells.get(key, {"calls": 0, "pax": 0})
        ships = int(cell.get("calls", 0) or 0)
        pax = int(cell.get("pax", 0) or 0)
        by_year.append(
            {
                "year": label,
                "period_key": key if not isinstance(key, int) else None,
                "ships": ships,
                "pax": pax,
            }
        )
        total_ships += ships
        total_pax += pax

    growth: list[dict[str, Any]] = []
    for idx, (_key, label) in enumerate(row_axis):
        pax = by_year[idx]["pax"]
        prev_idx = (
            prev_indices[idx]
            if prev_indices is not None
            else (idx - 1 if idx > 0 else None)
        )
        if prev_idx is None:
            pct = None
        else:
            pct = _growth_pct(pax, by_year[prev_idx]["pax"])
        growth.append({"year": label, "pct": pct})
    return {
        "by_year": by_year,
        "growth": growth,
        "total_ships": total_ships,
        "total_pax": total_pax,
    }


def _sum_axis_cells(
    line_data: dict[int, dict[Any, dict[str, int]]],
    line_ids: list[int],
    axis_keys: list[Any],
) -> dict[Any, dict[str, int]]:
    combined: dict[Any, dict[str, int]] = {
        key: {"calls": 0, "pax": 0} for key in axis_keys
    }
    for line_id in line_ids:
        for key in axis_keys:
            cell = line_data.get(line_id, {}).get(key, {"calls": 0, "pax": 0})
            combined[key]["calls"] += int(cell.get("calls", 0) or 0)
            combined[key]["pax"] += int(cell.get("pax", 0) or 0)
    return combined


def _growth_pct(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None if current <= 0 else 100.0
    return round(((current - previous) / previous) * 100)


def _build_trends_groups(
    *,
    line_ids: list[int],
    line_data: dict[int, dict[Any, dict[str, int]]],
    line_meta: dict[int, dict[str, Any]],
    line_logos: dict[int, str | None],
    row_axis: list[tuple[Any, Any]],
    axis_keys: list[Any],
    prev_indices: list[int | None] | None = None,
) -> list[dict[str, Any]]:
    groups_map: dict[int, dict[str, Any]] = {}
    for line_id in line_ids:
        info = line_meta.get(line_id, {})
        group_id = int(info.get("group_id") or 0)
        metrics = _trend_metrics_for_axis(
            line_data[line_id], row_axis, prev_indices=prev_indices
        )
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
    for group in groups_map.values():
        group["lines"].sort(
            key=lambda row: (
                -int(row.get("total_pax") or 0),
                (row.get("name") or "").lower(),
            )
        )
        lids = [int(line["shipping_line_id"]) for line in group["lines"]]
        group_metrics = _trend_metrics_for_axis(
            _sum_axis_cells(line_data, lids, axis_keys),
            row_axis,
            prev_indices=prev_indices,
        )
        groups.append({**group, **group_metrics})
    groups.sort(
        key=lambda row: (
            -int(row.get("total_pax") or 0),
            (row.get("name") or "").lower(),
        )
    )
    return groups


def _line_axis_metric_sum(
    line_data: dict[int, dict[Any, dict[str, int]]],
    line_id: int,
    metric: str,
) -> int:
    return sum(
        int(cell.get(metric, 0) or 0)
        for cell in line_data.get(line_id, {}).values()
    )


def _build_by_line_period(
    *,
    line_data: dict[int, dict[Any, dict[str, int]]],
    line_meta: dict[int, dict[str, Any]],
    row_axis: list[tuple[Any, Any]],
    focus_ids: list[int] | None,
    others_ids: list[int],
    limit: int = 8,
) -> dict[str, Any]:
    """Calls/PAX by shipping line along the report axis (years or seasons)."""
    labels = [str(label) for _key, label in row_axis]

    def series_for(line_id: int, name: str, code: str) -> dict[str, Any]:
        cells = line_data.get(line_id, {})
        return {
            "shipping_line_id": line_id,
            "name": name,
            "code": code,
            "points": [
                {
                    "key": key,
                    "label": str(label),
                    "calls": int(cells.get(key, {}).get("calls", 0) or 0),
                    "passengers": int(cells.get(key, {}).get("pax", 0) or 0),
                }
                for key, label in row_axis
            ],
        }

    lines_out: list[dict[str, Any]] = []
    if focus_ids is not None:
        ranked = sorted(
            focus_ids,
            key=lambda lid: (
                -_line_axis_metric_sum(line_data, lid, "pax"),
                (line_meta.get(lid, {}).get("name") or "").lower(),
            ),
        )
        for lid in ranked:
            info = line_meta.get(lid, {})
            lines_out.append(
                series_for(
                    lid,
                    info.get("name") or f"Línea {lid}",
                    info.get("code") or "",
                )
            )
        if others_ids:
            combined = _sum_axis_cells(
                line_data, others_ids, [key for key, _ in row_axis]
            )
            lines_out.append(
                {
                    "shipping_line_id": -1,
                    "name": "Otros",
                    "code": "",
                    "points": [
                        {
                            "key": key,
                            "label": str(label),
                            "calls": int(combined.get(key, {}).get("calls", 0) or 0),
                            "passengers": int(
                                combined.get(key, {}).get("pax", 0) or 0
                            ),
                        }
                        for key, label in row_axis
                    ],
                }
            )
    else:
        ranked = sorted(
            line_data.keys(),
            key=lambda lid: (
                -_line_axis_metric_sum(line_data, lid, "calls"),
                (line_meta.get(lid, {}).get("name") or "").lower(),
            ),
        )[:limit]
        for lid in ranked:
            info = line_meta.get(lid, {})
            lines_out.append(
                series_for(
                    lid,
                    info.get("name") or f"Línea {lid}",
                    info.get("code") or "",
                )
            )
    return {"labels": labels, "lines": lines_out}


def _daily_call_rows(qs) -> list[dict[str, Any]]:
    counts: dict[date, int] = defaultdict(int)
    for booking in qs.iterator(chunk_size=500):
        counts[booking.call_date] += 1
    return [
        {"date": day.isoformat(), "calls": counts[day]}
        for day in sorted(counts)
    ]


def build_port_trends(
    *,
    date_from: date,
    date_to: date,
    port_id: int,
    without_lta: bool = False,
    pax_basis: str = PAX_BASIS_PLANNED,
    shipping_line_ids: list[int] | None = None,
    shipping_line_group_ids: list[int] | None = None,
    season: str = SEASON_NATURAL,
    allowed_ports: set[int] | None = None,
    request=None,
    page: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    season_kind = normalize_panorama_season(season)
    use_seasons = season_kind != SEASON_NATURAL
    periods = (
        matrix_periods_for_range(date_from, date_to, season_kind)
        if use_seasons
        else []
    )
    years = years_in_range(date_from, date_to)
    if use_seasons:
        row_axis = _season_row_axis(periods)
        column_labels: list[Any] = [label for _key, label in row_axis]
    else:
        row_axis = _natural_row_axis(years)
        column_labels = list(years)
    axis_keys = [key for key, _ in row_axis]
    prev_indices = _axis_growth_prev_indices(row_axis, periods)

    # Full port scope — Otros needs bookings outside the carrier filter.
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        port_id=port_id,
        allowed_ports=allowed_ports,
        without_lta=without_lta,
        request=request,
    )
    if use_seasons:
        qs = _filter_qs_by_season(
            qs, date_from=date_from, date_to=date_to, season=season_kind
        )
        line_data, line_meta = _aggregate_trends_by_line_periods(
            qs, periods, pax_basis=pax_basis
        )
    else:
        line_data, line_meta = _aggregate_trends_by_line(qs, pax_basis=pax_basis)

    selected_ids = _resolve_selected_line_ids(
        shipping_line_ids=shipping_line_ids,
        shipping_line_group_ids=shipping_line_group_ids,
    )
    has_selection = bool(selected_ids)
    if has_selection:
        focus_ids = [lid for lid in line_data if lid in selected_ids]
        others_ids = [lid for lid in line_data if lid not in selected_ids]
    else:
        focus_ids = list(line_data.keys())
        others_ids = []

    line_logos = _line_logo_map(list(line_data.keys()), request)
    groups = _build_trends_groups(
        line_ids=focus_ids,
        line_data=line_data,
        line_meta=line_meta,
        line_logos=line_logos,
        row_axis=row_axis,
        axis_keys=axis_keys,
        prev_indices=prev_indices,
    )

    others_group: dict[str, Any] | None = None
    if has_selection and others_ids:
        others_lines = []
        for lid in sorted(
            others_ids,
            key=lambda i: (
                -_trend_metrics_for_axis(line_data[i], row_axis)["total_pax"],
                (line_meta.get(i, {}).get("name") or "").lower(),
            ),
        ):
            info = line_meta.get(lid, {})
            others_lines.append(
                {
                    "shipping_line_id": lid,
                    "code": info.get("code") or "",
                    "name": info.get("name") or f"Línea {lid}",
                    "logo": line_logos.get(lid),
                    **_trend_metrics_for_axis(
                        line_data[lid],
                        row_axis,
                        prev_indices=prev_indices,
                    ),
                }
            )
        others_metrics = _trend_metrics_for_axis(
            _sum_axis_cells(line_data, others_ids, axis_keys),
            row_axis,
            prev_indices=prev_indices,
        )
        others_group = {
            "shipping_line_group_id": -1,
            "is_others": True,
            "code": "",
            "name": "Otros",
            "lines": others_lines,
            **others_metrics,
        }

    totals = _trend_metrics_for_axis(
        _sum_axis_cells(line_data, list(line_data.keys()), axis_keys),
        row_axis,
        prev_indices=prev_indices,
    )

    page_groups, pagination = _paginate_items(
        groups,
        page=page,
        page_size=page_size,
        default_page_size=DEFAULT_TRENDS_LINE_PAGE_SIZE,
    )

    by_line_period = _build_by_line_period(
        line_data=line_data,
        line_meta=line_meta,
        row_axis=row_axis,
        focus_ids=focus_ids if has_selection else None,
        others_ids=others_ids,
    )
    daily_calls = {"days": _daily_call_rows(qs)}

    port = Port.objects.get(pk=port_id)
    port_logo = _media_url(request, port.logo)
    port_label = _port_friendly_name(port)
    growth_note = (
        "Growth % = variación Summer vs Summer y Winter vs Winter de PAX."
        if use_seasons
        else "Growth % = variación YoY de PAX."
    )
    note = f"{pax_basis_note(pax_basis)} {growth_note}"
    if use_seasons:
        span = _period_span_label(periods)
        if span:
            note = f"{note} Columnas: {span}."

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
        "season": season_kind,
        "years": years,
        "column_labels": column_labels,
        "periods": [p.as_dict() for p in periods] if use_seasons else [],
        "groups": page_groups,
        "others": others_group,
        "totals": totals,
        "by_line_period": by_line_period,
        "daily_calls": daily_calls,
        "note": note,
        **pagination,
    }


def _year_rows_metric(
    agg: dict[Any, dict[int, dict[str, int]]],
    row_axis: list[tuple[Any, Any]],
    metric: str,
    *,
    include_column_totals: bool = True,
    month_order: tuple[int, ...] = CALENDAR_MONTHS,
) -> list[dict[str, Any]]:
    """Build matrix rows. row_axis = [(agg_key, display_label), ...]."""
    rows: list[dict[str, Any]] = []
    month_totals = [0] * len(month_order)
    grand = 0
    for key, label in row_axis:
        months = []
        year_total = 0
        for index, month in enumerate(month_order):
            value = agg.get(key, {}).get(month, {}).get(metric, 0)
            months.append(value)
            month_totals[index] += value
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


def _cruise_year_key(year: int) -> str:
    return f"cruise-{year}"


def _cruise_year_label(year: int) -> str:
    return f"{year}/{year + 1}"


def _cruise_year_row_axis(periods) -> list[tuple[str, str]]:
    """One row per cruise year (May–Apr): Summer + Winter of the same start year."""
    seen: list[int] = []
    for period in periods:
        if period.year not in seen:
            seen.append(period.year)
    return [
        (_cruise_year_key(year), _cruise_year_label(year)) for year in seen
    ]


def _collapse_period_agg_to_cruise_year(data, periods):
    """entity -> period_key -> month  →  entity -> cruise-year -> month."""
    key_map = {period.key: _cruise_year_key(period.year) for period in periods}
    collapsed: dict[Any, dict[Any, dict[int, dict[str, int]]]] = defaultdict(
        _empty_keyed_months
    )
    for entity_id, keyed in data.items():
        for period_key, months in keyed.items():
            cruise_key = key_map.get(period_key)
            if cruise_key is None:
                continue
            dest_year = collapsed[entity_id][cruise_key]
            for month, cell in months.items():
                dest = dest_year[month]
                dest["calls"] += int(cell.get("calls") or 0)
                dest["pax"] += int(cell.get("pax") or 0)
    return collapsed


def _matrix_month_axis(use_seasons: bool) -> tuple[list[str], tuple[int, ...]]:
    if use_seasons:
        return list(CRUISE_YEAR_MONTH_LABELS), CRUISE_YEAR_MONTHS
    return list(MONTH_LABELS), CALENDAR_MONTHS


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
    month_order: tuple[int, ...] = CALENDAR_MONTHS,
    logo: str | None = None,
    logo_kind: str | None = None,
    logo_name: str | None = None,
    logo_path: str | None = None,
    port_id: int | None = None,
) -> dict[str, Any]:
    section: dict[str, Any] = {
        "label": label,
        "calls": _year_rows_metric(
            agg,
            row_axis,
            "calls",
            include_column_totals=include_column_totals,
            month_order=month_order,
        ),
        "pax": _year_rows_metric(
            agg,
            row_axis,
            "pax",
            include_column_totals=include_column_totals,
            month_order=month_order,
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
    if port_id:
        section["port_id"] = port_id
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
    """
    CALL/PAX matrices per port.

    Columns stay months. Rows are calendar years (natural) or one cruise-year
    row (May–Apr: Summer + Winter) when Temporadas is on.
    """
    season_kind = normalize_panorama_season(season)
    scoped_ports = _scope_allowed_ports(allowed_ports, port_ids)
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        allowed_ports=scoped_ports,
        without_lta=without_lta,
        request=request,
    )
    years = years_in_range(date_from, date_to)
    use_seasons = season_kind != SEASON_NATURAL
    periods = (
        matrix_periods_for_range(date_from, date_to, season_kind)
        if use_seasons
        else []
    )
    month_labels, month_order = _matrix_month_axis(use_seasons)
    if use_seasons:
        qs = _filter_qs_by_season(
            qs, date_from=date_from, date_to=date_to, season=season_kind
        )
        port_data, port_meta = _aggregate_by_port_periods(
            qs, periods, pax_basis=pax_basis
        )
        port_data = _collapse_period_agg_to_cruise_year(port_data, periods)
        row_axis = _cruise_year_row_axis(periods)
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
            month_order=month_order,
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
                month_order=month_order,
                logo=assets.get("url"),
                logo_name=assets.get("name"),
                logo_path=assets.get("path"),
                logo_kind="port",
                port_id=port_id,
            )
        )

    page_sections, pagination = _paginate_items(
        sections,
        page=page,
        page_size=page_size,
        default_page_size=DEFAULT_MATRIX_SECTION_PAGE_SIZE,
    )

    note = pax_basis_note(pax_basis)
    if use_seasons and row_axis:
        labels = [str(label) for _key, label in row_axis]
        span = labels[0] if len(labels) == 1 else f"{labels[0]}–{labels[-1]}"
        note = f"{note} Filas: {span}."

    return {
        "kind": "ports_totals",
        "title": "Bookings totals de puertos",
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "without_lta": without_lta,
        "pax_basis": pax_basis,
        "season": season_kind,
        "month_labels": month_labels,
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

    Columns stay months. Rows are calendar years (natural) or one cruise-year
    row (May–Apr: Summer + Winter) when Temporadas is on.
    """
    season_kind = normalize_panorama_season(season)
    port = Port.objects.get(pk=port_id)
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        port_id=port_id,
        allowed_ports=allowed_ports,
        without_lta=without_lta,
        request=request,
    )
    years = years_in_range(date_from, date_to)
    use_seasons = season_kind != SEASON_NATURAL
    periods = (
        matrix_periods_for_range(date_from, date_to, season_kind)
        if use_seasons
        else []
    )
    month_labels, month_order = _matrix_month_axis(use_seasons)
    if use_seasons:
        qs = _filter_qs_by_season(
            qs, date_from=date_from, date_to=date_to, season=season_kind
        )
        line_data, line_meta = _aggregate_by_line_periods(
            qs, periods, pax_basis=pax_basis
        )
        line_data = _collapse_period_agg_to_cruise_year(line_data, periods)
        row_axis = _cruise_year_row_axis(periods)
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
            month_order=month_order,
            logo=port_assets["url"],
            logo_name=port_assets["name"],
            logo_path=port_assets["path"],
            logo_kind="port",
            port_id=port.id,
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
                month_order=month_order,
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
                month_order=month_order,
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
    if use_seasons and row_axis:
        labels = [str(label) for _key, label in row_axis]
        span = labels[0] if len(labels) == 1 else f"{labels[0]}–{labels[-1]}"
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
        "month_labels": month_labels,
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
    month_labels: list[str] | tuple[str, ...] | None = None,
    banner_ports: list | None = None,
) -> int:
    col_span = 14
    row = write_report_banner(
        ws,
        start_row,
        title=title,
        subtitle=subtitle,
        col_span=col_span,
        ports=banner_ports,
    )
    for section in sections:
        write_section_banner(
            ws,
            row,
            section["label"],
            col_span,
            logo_path=section.get("logo_path"),
            logo_name=section.get("logo_name"),
        )
        row += 1
        write_matrix_header(
            ws,
            row,
            row_label=row_label_header,
            month_labels=tuple(month_labels or MONTH_LABELS),
        )
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
    month_labels = report.get("month_labels") or MONTH_LABELS
    from apps.bookings.services.arrivals_pdf.logo import ports_from_report_payload

    banner_ports = ports_from_report_payload(report)
    end_calls = _write_matrix_block(
        ws,
        1,
        title=calls_title,
        subtitle=subtitle or None,
        sections=report["sections"],
        metric_key="calls",
        row_label_header=row_header,
        month_labels=month_labels,
        banner_ports=banner_ports,
    )
    _write_matrix_block(
        ws,
        end_calls + 1,
        title=pax_title,
        subtitle=subtitle or None,
        sections=report["sections"],
        metric_key="pax",
        row_label_header=row_header,
        month_labels=month_labels,
        banner_ports=banner_ports,
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


def _trends_export_columns(report: dict[str, Any]) -> list[Any]:
    labels = report.get("column_labels")
    if labels:
        return list(labels)
    return list(report.get("years") or [])


def _trends_growth_export_title(report: dict[str, Any]) -> str:
    if report.get("season") and report.get("season") != SEASON_NATURAL:
        return "GROWTH PERCENTAGE (PAX Summer vs Summer / Winter vs Winter)"
    return "GROWTH PERCENTAGE (PAX YoY)"


def _trends_export_groups(report: dict[str, Any]) -> list[dict[str, Any]]:
    groups = list(report.get("groups") or [])
    others = report.get("others")
    if others:
        groups.append(others)
    return groups


def build_port_trends_xlsx(**kwargs) -> bytes:
    report = build_port_trends(**kwargs)
    years = _trends_export_columns(report)
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

    from apps.bookings.services.arrivals_pdf.logo import ports_from_report_payload

    report_ports = ports_from_report_payload(report)
    row = write_report_banner(
        ws,
        1,
        title=f"TRENDS — {port_name.upper()}",
        subtitle=subtitle or None,
        col_span=trends_cols,
        ports=report_ports,
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

    export_groups = _trends_export_groups(report)
    for g_idx, group in enumerate(export_groups):
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
    growth_title = _trends_growth_export_title(report)
    grow = write_report_banner(
        ws_g,
        1,
        title=growth_title,
        subtitle=subtitle or None,
        col_span=growth_cols,
        ports=report_ports,
    )
    g_header_row = grow
    write_column_header_band(
        ws_g, grow, ["Grupo / Naviera", *[str(y) for y in years]]
    )
    grow += 1
    g_body_start = grow

    for group in export_groups:
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
