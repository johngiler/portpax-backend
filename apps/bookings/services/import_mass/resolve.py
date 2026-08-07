"""Resolve ITM mass-import rows against PortPax catalogs + booking rules."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from typing import Any

from django.db.models import Q

from apps.bookings.constants import LTA_SOFT_FAIL_CODES
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.validation import validate_booking_params
from apps.catalogs.models import Port, Vessel

BULK_IMPORT_STATUSES = frozenset(
    {
        BookingStatus.H,
        BookingStatus.CO,
        BookingStatus.CL,
        BookingStatus.LTA,
        BookingStatus.LTD,
    }
)


def _normalize_bulk_status(raw: object) -> str:
    status = str(raw or BookingStatus.H).strip().lower()
    if status in BULK_IMPORT_STATUSES:
        return status
    return BookingStatus.H


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_port_token(raw: str) -> str:
    """'Roatan, Honduras' → 'roatan'."""
    text = (raw or "").split(",")[0].strip()
    text = _strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def resolve_port(port_raw: str) -> Port | None:
    token = normalize_port_token(port_raw)
    if not token:
        return None

    ports = list(Port.objects.filter(is_active=True))
    for port in ports:
        candidates = [
            normalize_port_token(port.name),
            normalize_port_token(port.commercial_name or ""),
            normalize_port_token(port.code.replace("_", " ")),
        ]
        if token in candidates or any(
            token == c or token in c or c in token for c in candidates if c
        ):
            return port

    qs = Port.objects.filter(is_active=True).filter(
        Q(name__icontains=token)
        | Q(commercial_name__icontains=token)
        | Q(code__icontains=token.replace(" ", "_"))
    )
    if qs.count() == 1:
        return qs.first()
    return None


def resolve_vessel(ship_raw: str) -> Vessel | None:
    name = re.sub(r"\s+", " ", (ship_raw or "").strip())
    if not name or len(name) < 2:
        return None

    exact = (
        Vessel.objects.filter(is_active=True, name__iexact=name)
        .select_related("shipping_line")
        .first()
    )
    if exact:
        return exact

    starts = list(
        Vessel.objects.filter(is_active=True, name__istartswith=name)
        .select_related("shipping_line")
        .order_by("name")[:5]
    )
    if len(starts) == 1:
        return starts[0]

    contains = list(
        Vessel.objects.filter(is_active=True, name__icontains=name)
        .select_related("shipping_line")
        .order_by("name")[:5]
    )
    if len(contains) == 1:
        return contains[0]
    return None


def _time_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%H:%M:%S")


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _catalog_blockers(issues: list[str]) -> bool:
    return any(
        msg.startswith("Falta")
        or "inválida" in msg
        or "no encontrado" in msg
        or msg.startswith("Ya existe")
        or msg.startswith("Duplicada en este archivo")
        or "Reclamar espacio LTA" in msg
        for msg in issues
    )


def _parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _claim_lta_space_flag(data: dict[str, Any] | None) -> bool:
    if not data:
        return False
    # Legacy import retry batches used replace_lta.
    return bool(data.get("claim_lta_space") or data.get("replace_lta"))


def _lta_space_candidate_payload(data: dict[str, Any] | None) -> Any:
    if not data:
        return None
    if "lta_space_candidate" in data:
        return data.get("lta_space_candidate")
    return data.get("lta_replace_candidate")


def _validate_import_booking(
    *,
    port: Port,
    vessel: Vessel,
    call_date: str,
    eta: str | None,
    etd: str | None,
    preferred_position_id: int | None,
    claim_lta_space: bool,
    issues: list[str],
    warnings: list[str],
    suggested_status: str,
) -> tuple[str, dict[str, Any]]:
    """
    Position suggestion, claimable LTA space detection, and booking validation.
    Returns (suggested_status, position/lta fields).
    """
    from apps.bookings.services.import_mass.position_lta import resolve_position_and_lta

    shipping_line_id = vessel.shipping_line_id
    if not shipping_line_id:
        issues.append("El barco no tiene naviera asignada.")
        return suggested_status, {
            "position_id": preferred_position_id,
            "position_code": None,
            "claim_lta_space": False,
            "lta_space_candidate": None,
            "lta_space_count": 0,
        }

    call_d = date.fromisoformat(call_date)
    pos = resolve_position_and_lta(
        port_id=port.id,
        vessel_id=vessel.id,
        shipping_line_id=shipping_line_id,
        call_date=call_d,
        preferred_position_id=preferred_position_id,
        claim_lta_space=claim_lta_space,
    )
    candidate = pos.get("lta_space_candidate")
    claiming = bool(claim_lta_space and candidate)

    existing = (
        Booking.objects.filter(
            port_id=port.id,
            vessel_id=vessel.id,
            call_date=call_d,
        )
        .select_related("vessel", "position", "port", "shipping_line")
        .first()
    )
    if existing is not None:
        if existing.status == BookingStatus.LTA:
            if not candidate:
                from apps.bookings.services.import_mass.position_lta import (
                    serialize_lta_space_candidate,
                )

                candidate = serialize_lta_space_candidate(existing)
                pos["lta_space_candidate"] = candidate
            if claiming:
                pass
            else:
                pos_label = ""
                if candidate and candidate.get("position_code"):
                    pos_label = f" en {candidate['position_code']}"
                issues.append(
                    f"Hay un espacio LTA de esta naviera ({existing.booking_code}"
                    f"{pos_label}). Marca «Reclamar espacio LTA» para actualizarlo "
                    "a Confirmada LTA (barco real si cambió)."
                )
        else:
            issues.append("Ya existe una reserva para este barco/puerto/fecha.")

    if candidate and not claiming and existing is None:
        line_name = candidate.get("shipping_line_name") or "esta naviera"
        pos_label = candidate.get("position_code") or "posición"
        issues.append(
            f"Hay un espacio LTA de {line_name} esperándote en {pos_label} "
            f"({candidate.get('booking_code')}). "
            "Marca «Reclamar espacio LTA» para actualizarlo a Confirmada LTA "
            "(el barco del LTA no tiene que coincidir)."
        )

    lta_count = int(pos.get("lta_space_count") or 0)
    if claiming and lta_count > 1:
        warn = (
            f"Hay {lta_count} reservas LTA de esta naviera en esta fecha; "
            "se reclamará la más antigua."
        )
        if warn not in warnings:
            warnings.append(warn)

    if claiming:
        suggested_status = BookingStatus.CL

    if not _catalog_blockers(issues):
        try:
            validation = validate_booking_params(
                port_id=port.id,
                vessel_id=vessel.id,
                call_dates=[call_d],
                position_id=pos.get("position_id"),
                eta=_parse_time(eta),
                etd=_parse_time(etd),
            )
        except Exception:
            issues.append("No se pudo validar la reserva.")
        else:
            skip_codes = set()
            if claiming:
                skip_codes.add("position_occupied")
            for err in validation.get("errors") or []:
                if not isinstance(err, dict):
                    issues.append(str(err))
                    continue
                msg = err.get("message") or ""
                code = err.get("code") or ""
                if not msg:
                    continue
                if code in skip_codes:
                    continue
                if code in LTA_SOFT_FAIL_CODES:
                    soft_msg = f"{msg} Se puede crear en evaluación (Hold)."
                    if soft_msg not in warnings:
                        warnings.append(soft_msg)
                    suggested_status = BookingStatus.H
                else:
                    if msg not in issues:
                        issues.append(msg)
            for warn in validation.get("warnings") or []:
                msg = warn.get("message") if isinstance(warn, dict) else str(warn)
                if msg and msg not in warnings:
                    warnings.append(msg)

    pos["claim_lta_space"] = claiming
    return suggested_status, pos


def resolve_itm_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach catalog matches, booking validation, and selectable flag."""
    resolved: list[dict[str, Any]] = []
    seen_keys: set[tuple[int, int, str]] = set()

    for raw in raw_rows:
        ship = raw.get("ship") or ""
        port_raw = raw.get("port_raw") or ""
        arrival: datetime | None = raw.get("arrival")
        departure: datetime | None = raw.get("departure")
        row_number = raw.get("row_number")

        issues: list[str] = []
        warnings: list[str] = []
        suggested_status = BookingStatus.H
        position_fields: dict[str, Any] = {
            "position_id": None,
            "position_code": None,
            "claim_lta_space": False,
            "lta_space_candidate": None,
        }

        if not ship:
            issues.append("Falta el barco (Ship).")
        if not port_raw:
            issues.append("Falta el puerto (Port).")
        if arrival is None:
            issues.append("Fecha/hora de Arrival inválida.")
        if departure is None:
            issues.append("Fecha/hora de Departure inválida.")

        port = resolve_port(port_raw) if port_raw else None
        vessel = resolve_vessel(ship) if ship else None

        if port_raw and port is None:
            issues.append(f"Puerto no encontrado: «{port_raw}».")
        if ship and vessel is None:
            issues.append(f"Barco no encontrado: «{ship}».")

        call_date = arrival.date().isoformat() if arrival else None
        eta = _time_iso(arrival)
        etd = _time_iso(departure)

        if port and vessel and call_date:
            key = (port.id, vessel.id, call_date)
            if key in seen_keys:
                issues.append(
                    "Duplicada en este archivo (mismo barco, puerto y fecha)."
                )
            else:
                seen_keys.add(key)

            if not any(
                msg.startswith("Duplicada")
                or msg.startswith("Falta")
                or "inválida" in msg
                or "no encontrado" in msg
                for msg in issues
            ):
                suggested_status, position_fields = _validate_import_booking(
                    port=port,
                    vessel=vessel,
                    call_date=call_date,
                    eta=eta,
                    etd=etd,
                    preferred_position_id=_parse_optional_int(raw.get("position_id")),
                    claim_lta_space=_claim_lta_space_flag(raw),
                    issues=issues,
                    warnings=warnings,
                    suggested_status=suggested_status,
                )

        selectable = (
            port is not None
            and vessel is not None
            and call_date is not None
            and eta is not None
            and etd is not None
            and len(issues) == 0
        )

        resolved.append(
            {
                "id": f"r{row_number}",
                "row_number": row_number,
                "ship": ship,
                "port_raw": port_raw,
                "vendor_name": raw.get("vendor_name") or "",
                "call_type": raw.get("call_type") or "",
                "call_date": call_date,
                "eta": eta,
                "etd": etd,
                "port_id": port.id if port else None,
                "port_name": port.name if port else None,
                "port_code": port.code if port else None,
                "vessel_id": vessel.id if vessel else None,
                "vessel_name": vessel.name if vessel else None,
                "shipping_line_id": vessel.shipping_line_id if vessel else None,
                "shipping_line_name": vessel.shipping_line.name if vessel else None,
                "suggested_status": _normalize_bulk_status(suggested_status),
                "position_id": position_fields.get("position_id"),
                "position_code": position_fields.get("position_code"),
                "claim_lta_space": bool(position_fields.get("claim_lta_space")),
                "lta_space_candidate": position_fields.get("lta_space_candidate"),
                "issues": issues,
                "warnings": warnings,
                "selectable": selectable,
                "selected_default": selectable,
            }
        )

    return resolved


def resolve_preview_row_edit(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Re-validate one preview row after manual edits.
    Prefers port_id / vessel_id when set; otherwise fuzzy-matches ship / port_raw.
    Preserves suggested_status from client unless LTA soft-fail forces Hold.
    """
    row_number = payload.get("row_number") or 0
    try:
        row_number = int(row_number)
    except (TypeError, ValueError):
        row_number = 0

    ship = str(payload.get("ship") or payload.get("vessel_name") or "").strip()
    port_raw = str(payload.get("port_raw") or payload.get("port_name") or "").strip()
    call_date_raw = payload.get("call_date")
    eta = payload.get("eta")
    etd = payload.get("etd")
    if isinstance(eta, str):
        eta = eta.strip() or None
        if eta and len(eta) == 5:
            eta = f"{eta}:00"
    if isinstance(etd, str):
        etd = etd.strip() or None
        if etd and len(etd) == 5:
            etd = f"{etd}:00"

    arrival = None
    departure = None
    if call_date_raw and eta:
        try:
            arrival = datetime.combine(
                date.fromisoformat(str(call_date_raw)[:10]),
                _parse_time(eta) or time(0, 0),
            )
        except ValueError:
            arrival = None
    if call_date_raw and etd:
        try:
            departure = datetime.combine(
                date.fromisoformat(str(call_date_raw)[:10]),
                _parse_time(etd) or time(0, 0),
            )
        except ValueError:
            departure = None

    raw = {
        "ship": ship,
        "port_raw": port_raw,
        "arrival": arrival,
        "departure": departure,
        "vendor_name": payload.get("vendor_name") or "",
        "call_type": payload.get("call_type") or "",
        "row_number": row_number,
    }
    resolved = resolve_itm_rows([raw])[0]

    # Force catalog picks from the editor when provided.
    port_id = payload.get("port_id")
    vessel_id = payload.get("vessel_id")
    if port_id or vessel_id or payload.get("shipping_line_id"):
        issues: list[str] = []
        # Fresh list — resolve_itm_rows above already ran validation; do not keep
        # those warnings or LTA soft-fails appear twice after revalidate.
        warnings: list[str] = []
        suggested_status = _normalize_bulk_status(
            payload.get("suggested_status") or BookingStatus.H
        )

        port = None
        vessel = None
        shipping_line = None
        line_id = payload.get("shipping_line_id")
        if line_id:
            from apps.catalogs.models import ShippingLine

            shipping_line = ShippingLine.objects.filter(
                pk=line_id, is_active=True
            ).first()
            if shipping_line is None:
                issues.append("Naviera no válida.")

        if port_id:
            port = Port.objects.filter(pk=port_id, is_active=True).first()
            if port is None:
                issues.append("Puerto no válido.")
        elif port_raw:
            port = resolve_port(port_raw)
            if port is None:
                issues.append(f"Puerto no encontrado: «{port_raw}».")

        if vessel_id:
            vessel = (
                Vessel.objects.filter(pk=vessel_id, is_active=True)
                .select_related("shipping_line")
                .first()
            )
            if vessel is None:
                issues.append("Barco no válido.")
            elif shipping_line and vessel.shipping_line_id != shipping_line.id:
                issues.append("El barco no pertenece a la naviera seleccionada.")
            elif vessel and shipping_line is None:
                shipping_line = vessel.shipping_line
        elif ship:
            vessel = resolve_vessel(ship)
            if vessel is None:
                issues.append(f"Barco no encontrado: «{ship}».")
            elif shipping_line and vessel.shipping_line_id != shipping_line.id:
                issues.append("El barco no pertenece a la naviera seleccionada.")
            elif vessel and shipping_line is None:
                shipping_line = vessel.shipping_line

        call_date = str(call_date_raw)[:10] if call_date_raw else None
        if not call_date:
            issues.append("Fecha inválida.")
        if not eta:
            issues.append("ETA inválida.")
        if not etd:
            issues.append("ETD inválida.")

        if port and vessel and call_date and not any(
            msg.startswith("Falta")
            or "inválida" in msg
            or "no válido" in msg
            or "no encontrada" in msg
            or "no pertenece" in msg
            for msg in issues
        ):
            suggested_status, position_fields = _validate_import_booking(
                port=port,
                vessel=vessel,
                call_date=call_date,
                eta=eta,
                etd=etd,
                preferred_position_id=_parse_optional_int(payload.get("position_id")),
                claim_lta_space=_claim_lta_space_flag(payload),
                issues=issues,
                warnings=warnings,
                suggested_status=suggested_status,
            )
        else:
            position_fields = {
                "position_id": _parse_optional_int(payload.get("position_id")),
                "position_code": payload.get("position_code"),
                "claim_lta_space": _claim_lta_space_flag(payload),
                "lta_space_candidate": _lta_space_candidate_payload(payload),
            }

        selectable = (
            port is not None
            and vessel is not None
            and shipping_line is not None
            and call_date is not None
            and eta is not None
            and etd is not None
            and len(issues) == 0
        )
        resolved = {
            "id": str(payload.get("id") or f"r{row_number}"),
            "row_number": row_number,
            "ship": vessel.name if vessel else ship,
            "port_raw": port.name if port else port_raw,
            "vendor_name": payload.get("vendor_name") or "",
            "call_type": payload.get("call_type") or "",
            "call_date": call_date,
            "eta": eta,
            "etd": etd,
            "port_id": port.id if port else None,
            "port_name": port.name if port else None,
            "port_code": port.code if port else None,
            "vessel_id": vessel.id if vessel else None,
            "vessel_name": vessel.name if vessel else None,
            "shipping_line_id": shipping_line.id if shipping_line else None,
            "shipping_line_name": shipping_line.name if shipping_line else None,
            "suggested_status": _normalize_bulk_status(suggested_status),
            "position_id": position_fields.get("position_id"),
            "position_code": position_fields.get("position_code"),
            "claim_lta_space": bool(position_fields.get("claim_lta_space")),
            "lta_space_candidate": position_fields.get("lta_space_candidate"),
            "issues": issues,
            "warnings": warnings,
            "selectable": selectable,
            "selected_default": selectable,
        }
    else:
        resolved["suggested_status"] = _normalize_bulk_status(
            payload.get("suggested_status") or resolved.get("suggested_status")
        )
        resolved["id"] = str(payload.get("id") or resolved["id"])
        resolved["position_id"] = _parse_optional_int(payload.get("position_id")) or resolved.get(
            "position_id"
        )
        resolved["position_code"] = payload.get("position_code") or resolved.get("position_code")
        resolved["claim_lta_space"] = _claim_lta_space_flag(payload)
        candidate = _lta_space_candidate_payload(payload)
        if candidate is not None or "lta_space_candidate" in payload or "lta_replace_candidate" in payload:
            resolved["lta_space_candidate"] = candidate

    return resolved
