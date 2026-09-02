"""Vessel × port × date proximity matrix for bookings workspace."""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

from apps.accounts.permissions import user_port_ids
from apps.bookings.constants import ACTIVE_BOOKING_STATUSES
from apps.bookings.models import Booking
from apps.bookings.services.validation.conflict_display import (
    booking_conflict_display,
    booking_conflict_filter_ctx,
    cell_matches_conflict_filter,
)
from apps.bookings.services.validation.conflict_type_filters import CONFLICT_TYPES
from apps.bookings.utils.status_query import apply_booking_status_filters, parse_status_query_params
from apps.catalogs.models import Port, Vessel
from apps.catalogs.utils.position_code import position_short_code

MAX_MATRIX_WINDOW_DAYS = 93
MAX_MATRIX_RANGE_DAYS = 1100
DEFAULT_MATRIX_PAGE_SIZE = 30

PROXIMITY_CODES = frozenset({"multi_port_proximity", "multi_port_conflict"})


def _parse_iso_date(raw: str | None, field: str) -> date | None:
    if not raw or not str(raw).strip():
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"Invalid {field}.") from exc


def _cell_status_from_snapshot(snapshot: list | None) -> str:
    codes = {str(item.get("code") or "") for item in (snapshot or []) if isinstance(item, dict)}
    if "multi_port_conflict" in codes:
        return "same_day"
    if "multi_port_proximity" in codes:
        return "proximity"
    return "ok"


def _geo_issues_from_snapshot(snapshot: list | None) -> list[dict]:
    issues: list[dict] = []
    for item in snapshot or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "")
        if code not in PROXIMITY_CODES:
            continue
        issues.append(
            {
                "severity": str(item.get("severity") or "yellow"),
                "code": code,
                "message": str(item.get("message") or ""),
            }
        )
    return issues


def _file_url(request, field) -> str | None:
    if not field:
        return None
    try:
        url = field.url
    except ValueError:
        return None
    if request:
        return request.build_absolute_uri(url)
    return url


def _serialize_cell(booking, request) -> dict:
    position_code = None
    if booking.position_id and booking.port_id:
        position_code = position_short_code(booking.port.code, booking.position.code)

    snapshot = booking.conflict_snapshot or []
    conflict_display = booking_conflict_display(
        has_conflict=bool(booking.has_conflict),
        conflict_severity=booking.conflict_severity,
        snapshot=snapshot,
    )

    return {
        "date": booking.call_date.isoformat(),
        "port_id": booking.port_id,
        "booking_id": booking.id,
        "booking_code": booking.booking_code,
        "status": booking.status,
        "port_name": booking.port.name if booking.port_id else "",
        "vessel_name": booking.vessel.name,
        "vessel_logo": _file_url(request, booking.vessel.logo),
        "shipping_line_name": (
            booking.shipping_line.name if booking.shipping_line_id else ""
        ),
        "loa_m": str(booking.vessel.loa_m) if booking.vessel.loa_m is not None else None,
        "eta": booking.eta.isoformat() if booking.eta else None,
        "etd": booking.etd.isoformat() if booking.etd else None,
        "actual_pax": booking.actual_pax,
        "position_code": position_code,
        "conflict_chips": conflict_display["conflict_chips"],
        "conflict_highlights": conflict_display["conflict_highlights"],
        "cell_status": _cell_status_from_snapshot(snapshot),
        "issues": _geo_issues_from_snapshot(snapshot),
    }


def build_vessel_proximity_matrix(
    *,
    user,
    request=None,
    vessel_id: int,
    call_date_from: date,
    call_date_to: date,
    status_values: list[str] | None = None,
    port_id: int | None = None,
    has_conflict: bool | None = None,
    conflict_severity: str | None = None,
    conflict_type: str | None = None,
    call_dates: list[date] | None = None,
    page: int | None = None,
    page_size: int = DEFAULT_MATRIX_PAGE_SIZE,
) -> dict:
    if call_date_to < call_date_from:
        raise ValueError("call_date_to must be on or after call_date_from.")

    span_days = (call_date_to - call_date_from).days + 1
    if page is not None:
        if page < 1:
            raise ValueError("page must be >= 1.")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100.")
        if span_days > MAX_MATRIX_RANGE_DAYS:
            raise ValueError(f"Date range exceeds {MAX_MATRIX_RANGE_DAYS} days.")
    elif span_days > MAX_MATRIX_WINDOW_DAYS:
        raise ValueError(f"Date range exceeds {MAX_MATRIX_WINDOW_DAYS} days.")

    vessel = Vessel.objects.select_related("shipping_line").filter(pk=vessel_id).first()
    if vessel is None:
        raise ValueError("Vessel not found.")

    allowed_ports = user_port_ids(user)

    qs = Booking.objects.filter(
        vessel_id=vessel_id,
        call_date__gte=call_date_from,
        call_date__lte=call_date_to,
    ).select_related(
        "port",
        "vessel",
        "vessel__shipping_line",
        "shipping_line",
        "position",
    )

    if allowed_ports is not None:
        qs = qs.filter(port_id__in=allowed_ports)

    statuses = status_values if status_values else list(ACTIVE_BOOKING_STATUSES)
    qs = apply_booking_status_filters(qs, statuses)

    allow_dates = set(call_dates or [])
    if allow_dates:
        qs = qs.filter(call_date__in=allow_dates)

    bookings = list(qs.order_by("call_date", "id"))

    # Always expose every accessible port as a column (empty cells if no call).
    # Filtering by conflict/status only affects cells, not which ports appear.
    ports_qs = Port.objects.filter(is_active=True).order_by("name")
    if allowed_ports is not None:
        ports_qs = ports_qs.filter(id__in=allowed_ports)
    if port_id:
        ports_qs = ports_qs.filter(id=port_id)
    ports = list(ports_qs)

    cells = []
    conflict_filter_active = (
        has_conflict is not None
        or conflict_severity in {"yellow", "red", "green"}
        or conflict_type in CONFLICT_TYPES
    )

    for booking in bookings:
        if port_id and booking.port_id != port_id:
            continue
        filter_ctx = booking_conflict_filter_ctx(booking)
        if conflict_filter_active and not cell_matches_conflict_filter(
            filter_ctx,
            has_conflict=has_conflict,
            conflict_severity=conflict_severity,
            conflict_type=conflict_type,
        ):
            continue
        cells.append(_serialize_cell(booking, request))

    dates_with_cells = sorted({cell["date"] for cell in cells})
    port_payload = [
        {
            "id": port.id,
            "name": port.name,
            "code": port.code,
        }
        for port in ports
    ]
    base = {
        "vessel_id": vessel.id,
        "vessel_name": vessel.name,
        "shipping_line_id": vessel.shipping_line_id,
        "shipping_line_name": vessel.shipping_line.name if vessel.shipping_line_id else "",
        "date_from": call_date_from.isoformat(),
        "date_to": call_date_to.isoformat(),
        "ports": port_payload,
    }

    if page is not None:
        matched_total = len(dates_with_cells)
        start = (page - 1) * page_size
        end = start + page_size
        page_dates = dates_with_cells[start:end]
        page_date_set = set(page_dates)
        page_cells = [cell for cell in cells if cell["date"] in page_date_set]
        return {
            **base,
            "dates": page_dates,
            "cells": page_cells,
            "matched_days": matched_total,
            "page": page,
            "page_size": page_size,
            "has_more": end < matched_total,
        }

    return {
        **base,
        "dates": dates_with_cells,
        "cells": cells,
    }


def parse_vessel_proximity_matrix_params(query_params) -> dict:
    vessel_raw = query_params.get("vessel")
    if not vessel_raw:
        raise ValueError("vessel is required.")
    try:
        vessel_id = int(vessel_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid vessel.") from exc
    if vessel_id <= 0:
        raise ValueError("Invalid vessel.")

    call_date_from = _parse_iso_date(query_params.get("call_date_from"), "call_date_from")
    call_date_to = _parse_iso_date(query_params.get("call_date_to"), "call_date_to")
    if call_date_from is None:
        call_date_from = timezone.localdate()
    if call_date_to is None:
        call_date_to = call_date_from + timedelta(days=30)

    port_id = None
    port_raw = query_params.get("port")
    if port_raw:
        try:
            parsed_port = int(port_raw)
            if parsed_port > 0:
                port_id = parsed_port
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid port.") from exc

    status_values = parse_status_query_params(query_params)

    has_conflict = None
    has_conflict_raw = query_params.get("has_conflict")
    if has_conflict_raw is not None and str(has_conflict_raw).strip() != "":
        has_conflict = str(has_conflict_raw).strip().lower() in {
            "1",
            "true",
            "yes",
            "si",
            "sí",
        }

    conflict_severity = str(
        query_params.get("conflict_severity") or ""
    ).strip().lower()
    if conflict_severity not in {"yellow", "red", "green"}:
        conflict_severity = None

    conflict_type = str(query_params.get("conflict_type") or "").strip().lower()
    if conflict_type not in CONFLICT_TYPES:
        conflict_type = None

    from apps.bookings.utils.call_dates_query import parse_call_dates_param

    call_dates = parse_call_dates_param(query_params.get("call_dates"))

    page = None
    page_raw = query_params.get("page")
    if page_raw is not None and str(page_raw).strip() != "":
        try:
            page = int(page_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid page.") from exc

    page_size = DEFAULT_MATRIX_PAGE_SIZE
    page_size_raw = query_params.get("page_size")
    if page_size_raw is not None and str(page_size_raw).strip() != "":
        try:
            page_size = int(page_size_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid page_size.") from exc

    return {
        "vessel_id": vessel_id,
        "call_date_from": call_date_from,
        "call_date_to": call_date_to,
        "status_values": status_values,
        "port_id": port_id,
        "has_conflict": has_conflict,
        "conflict_severity": conflict_severity,
        "conflict_type": conflict_type,
        "call_dates": call_dates or None,
        "page": page,
        "page_size": page_size,
    }
