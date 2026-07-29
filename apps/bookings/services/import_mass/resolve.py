"""Resolve ITM mass-import rows against PortPax catalogs + booking rules."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from typing import Any

from django.db.models import Q

from apps.bookings.models import Booking
from apps.bookings.services.validation import validate_booking_params
from apps.catalogs.models import Port, Vessel


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
        for msg in issues
    )


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

            already_exists = Booking.objects.filter(
                port_id=port.id,
                vessel_id=vessel.id,
                call_date=call_date,
            ).exists()
            if already_exists:
                issues.append("Ya existe una reserva para este barco/puerto/fecha.")

            if not _catalog_blockers(issues):
                eta_t = _parse_time(eta)
                etd_t = _parse_time(etd)
                try:
                    validation = validate_booking_params(
                        port_id=port.id,
                        vessel_id=vessel.id,
                        call_dates=[date.fromisoformat(call_date)],
                        eta=eta_t,
                        etd=etd_t,
                    )
                except Exception:
                    issues.append("No se pudo validar la reserva.")
                else:
                    for err in validation.get("errors") or []:
                        msg = err.get("message") if isinstance(err, dict) else str(err)
                        if msg:
                            issues.append(msg)
                    for warn in validation.get("warnings") or []:
                        msg = warn.get("message") if isinstance(warn, dict) else str(warn)
                        if msg:
                            warnings.append(msg)

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
                "issues": issues,
                "warnings": warnings,
                "selectable": selectable,
                "selected_default": selectable,
            }
        )

    return resolved
