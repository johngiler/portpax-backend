"""Match recap rows to existing bookings (±1 day on the call date)."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

from apps.bookings.models import Booking
from apps.bookings.services.import_mass.resolve import (
    resolve_port,
    resolve_shipping_line,
    resolve_vessel,
)
from apps.bookings.services.validation.legend_labels import port_legend_label

_WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
_MONTHS = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)
_DATE_WINDOW = timedelta(days=1)


def _date_label(value: date) -> str:
    return f"{_WEEKDAYS[value.weekday()]} {value.day} {_MONTHS[value.month - 1]} {value.year}"


def _hhmm(value: time | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%H:%M")


def _port_label(port) -> str:
    label = port_legend_label(port).strip()
    return label or (getattr(port, "name", None) or "Puerto")


def _join_clauses(parts: list[str]) -> str:
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return f"{', '.join(parts[:-1])} y {parts[-1]}"


def _match_summary(booking: Booking, row: dict[str, Any]) -> tuple[int, str]:
    """Percent plus a Spanish sentence of which schedule fields agreed."""
    clauses: list[str] = []
    points = 0.0
    total = 0.0
    imported_date = row.get("call_date")
    if isinstance(imported_date, date):
        total += 1
        if booking.call_date == imported_date:
            points += 1
            clauses.append("la fecha coincide")
        else:
            points += 0.5
            clauses.append("la fecha está a un día (cuenta la mitad)")
    hits: list[str] = []
    misses: list[str] = []
    for label, current, imported in (
        ("la llegada", booking.eta, row.get("eta")),
        ("la salida", booking.etd, row.get("etd")),
    ):
        if not isinstance(imported, time):
            continue
        total += 1
        if _hhmm(current) == _hhmm(imported):
            points += 1
            hits.append(label)
        else:
            misses.append(label)
    if hits == ["la llegada", "la salida"]:
        clauses.append("la llegada y la salida coinciden")
    else:
        clauses.extend(f"{label} coincide" for label in hits)
    if misses == ["la llegada", "la salida"]:
        clauses.append("la llegada y la salida no coinciden")
    else:
        clauses.extend(f"{label} no coincide" for label in misses)
    percent = 100 if total == 0 else int(round(100 * points / total))
    because = _join_clauses(clauses) or "el barco y el puerto coinciden"
    return percent, f"{percent}% porque {because}."


def _avisos(booking: Booking, row: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    imported_date = row.get("call_date")
    if isinstance(imported_date, date) and booking.call_date != imported_date:
        notes.append(
            f"Fecha: PortPax {_date_label(booking.call_date)} · "
            f"recap {_date_label(imported_date)}"
        )
    for label, current, imported in (
        ("Llegada", booking.eta, row.get("eta")),
        ("Salida", booking.etd, row.get("etd")),
    ):
        if imported is None:
            continue
        current_label = _hhmm(current) or "—"
        imported_label = _hhmm(imported) or "—"
        if current_label != imported_label:
            notes.append(f"{label}: PortPax {current_label} · recap {imported_label}")
    return notes


def _candidate_key(booking: Booking, row: dict[str, Any]) -> tuple[int, int, int]:
    imported_date = row["call_date"]
    day_delta = abs((booking.call_date - imported_date).days)
    time_miss = 0
    if row.get("eta") is not None and _hhmm(booking.eta) != _hhmm(row.get("eta")):
        time_miss += 1
    if row.get("etd") is not None and _hhmm(booking.etd) != _hhmm(row.get("etd")):
        time_miss += 1
    return (day_delta, time_miss, booking.id)


def match_recap_rows(
    rows: list[dict[str, Any]],
    *,
    allowed_ports: set[int] | list[int] | None = None,
) -> dict[str, Any]:
    """Pair each recap row with at most one booking. Date may be ±1 day."""
    allowed = set(allowed_ports) if allowed_ports is not None else None
    prepared: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    for row in rows:
        ship = (row.get("ship") or "").strip()
        port_raw = (row.get("port_raw") or "").strip()
        line_raw = str(
            row.get("line_raw") or row.get("group_raw") or ""
        ).strip()
        call_date = row.get("call_date")
        base = {
            "row_number": row.get("row_number"),
            "ship": ship,
            "port": port_raw,
            "line": line_raw or None,
            "call_date": call_date.isoformat() if isinstance(call_date, date) else None,
            "eta": _hhmm(row.get("eta")) if isinstance(row.get("eta"), time) else None,
            "etd": _hhmm(row.get("etd")) if isinstance(row.get("etd"), time) else None,
        }
        if not isinstance(call_date, date):
            unmatched.append({**base, "reason": "Fecha de escala no válida."})
            continue
        port = resolve_port(port_raw)
        line = resolve_shipping_line(line_raw) if line_raw else None
        if line_raw and line is None:
            unmatched.append(
                {**base, "reason": f"Naviera no encontrada: «{line_raw}»."}
            )
            continue
        vessel = (
            resolve_vessel(
                ship,
                line.id if line is not None else None,
            )
            if ship
            else None
        )
        if port is None:
            unmatched.append({**base, "reason": f"Puerto no encontrado: «{port_raw}»."})
            continue
        if allowed is not None and port.id not in allowed:
            unmatched.append({**base, "reason": f"Sin acceso a {_port_label(port)}."})
            continue
        if vessel is None:
            if line is not None:
                unmatched.append(
                    {
                        **base,
                        "reason": (
                            f"Barco no encontrado en la naviera «{line.name}»: «{ship}»."
                        ),
                    }
                )
            else:
                unmatched.append({**base, "reason": f"Barco no encontrado: «{ship}»."})
            continue
        window_start = call_date - _DATE_WINDOW
        window_end = call_date + _DATE_WINDOW
        candidates = list(
            Booking.objects.filter(
                vessel_id=vessel.id,
                port_id=port.id,
                call_date__gte=window_start,
                call_date__lte=window_end,
            )
            .select_related("vessel", "port")
            .order_by("call_date", "id")
        )
        if not candidates:
            unmatched.append(
                {
                    **base,
                    "reason": (
                        f"Sin reserva de {vessel.name} en {_port_label(port)} "
                        f"el {_date_label(call_date)} (±1 día)."
                    ),
                }
            )
            continue
        prepared.append({"row": row, "candidates": candidates})

    prepared.sort(key=lambda item: _candidate_key(item["candidates"][0], item["row"]))
    used: set[int] = set()
    matches: list[dict[str, Any]] = []
    for item in prepared:
        row = item["row"]
        ranked = sorted(item["candidates"], key=lambda booking: _candidate_key(booking, row))
        chosen = next((booking for booking in ranked if booking.id not in used), None)
        call_date = row["call_date"]
        if chosen is None:
            unmatched.append(
                {
                    "row_number": row.get("row_number"),
                    "ship": row.get("ship") or "",
                    "port": row.get("port_raw") or "",
                    "line": (
                        str(row.get("line_raw") or row.get("group_raw") or "").strip()
                        or None
                    ),
                    "call_date": call_date.isoformat() if isinstance(call_date, date) else None,
                    "eta": _hhmm(row.get("eta")) if isinstance(row.get("eta"), time) else None,
                    "etd": _hhmm(row.get("etd")) if isinstance(row.get("etd"), time) else None,
                    "reason": "Esa reserva ya quedó emparejada con otra fila del recap.",
                }
            )
            continue
        used.add(chosen.id)
        avisos = _avisos(chosen, row)
        match_percent, match_reason = _match_summary(chosen, row)
        matches.append(
            {
                "booking_id": chosen.id,
                "booking_code": chosen.booking_code,
                "match": "exact" if not avisos else "approx",
                "match_percent": match_percent,
                "match_reason": match_reason,
                "avisos": avisos,
            }
        )

    unmatched.sort(key=lambda item: item.get("row_number") or 0)
    return {
        "imported_count": len(rows),
        "matched_count": len(matches),
        "matches": matches,
        "unmatched": unmatched,
    }
