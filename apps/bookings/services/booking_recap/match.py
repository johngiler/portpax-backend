"""Match recap rows to existing bookings (±1 day on the call date)."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

from apps.bookings.models import Booking
from apps.bookings.services.booking_recap.portpax_only import (
    find_portpax_only_bookings,
)
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


def _normalize_id_list(raw: list[int] | None) -> list[int]:
    out: list[int] = []
    for value in list(raw or []):
        try:
            n = int(value)
        except (TypeError, ValueError):
            continue
        if n > 0 and n not in out:
            out.append(n)
    return out


def match_recap_rows(
    rows: list[dict[str, Any]],
    *,
    allowed_ports: set[int] | list[int] | None = None,
    shipping_line_ids: list[int] | None = None,
    shipping_line_group_ids: list[int] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """
    Pair each recap row with at most one booking. Date may be ±1 day.

    Includes cancelled bookings (no status filter). Optional delimiters
    (group / lines / date range) narrow the candidate search.
    """
    allowed = set(allowed_ports) if allowed_ports is not None else None
    line_ids = _normalize_id_list(shipping_line_ids)
    group_ids = _normalize_id_list(shipping_line_group_ids)
    # Lines win over groups (same rule as list filters).
    effective_group_ids = [] if line_ids else group_ids
    prepared: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    # Ports / lines seen in the paste — bias for PortPax-only elasticity.
    recap_port_ids: set[int] = set()
    recap_line_ids: set[int] = set()

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
        # Collect paste bias even if the row later fails date / identity checks.
        port = resolve_port(port_raw)
        if port is not None:
            recap_port_ids.add(port.id)
        line = resolve_shipping_line(line_raw) if line_raw else None
        if line is not None:
            recap_line_ids.add(line.id)
        if not isinstance(call_date, date):
            unmatched.append({**base, "reason": "Fecha de escala no válida."})
            continue
        if date_from and call_date < date_from:
            unmatched.append(
                {
                    **base,
                    "reason": (
                        f"Fecha fuera del rango del recap "
                        f"(desde {_date_label(date_from)})."
                    ),
                }
            )
            continue
        if date_to and call_date > date_to:
            unmatched.append(
                {
                    **base,
                    "reason": (
                        f"Fecha fuera del rango del recap "
                        f"(hasta {_date_label(date_to)})."
                    ),
                }
            )
            continue
        if line_raw and line is None:
            unmatched.append(
                {**base, "reason": f"Naviera no encontrada: «{line_raw}»."}
            )
            continue
        if line is not None:
            if line_ids and line.id not in line_ids:
                unmatched.append(
                    {
                        **base,
                        "reason": (
                            f"Naviera «{line.name}» fuera de los delimitantes "
                            f"del recap."
                        ),
                    }
                )
                continue
            if (
                effective_group_ids
                and getattr(line, "group_id", None) not in effective_group_ids
            ):
                unmatched.append(
                    {
                        **base,
                        "reason": (
                            f"Naviera «{line.name}» fuera del grupo delimitado "
                            f"del recap."
                        ),
                    }
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
        vessel_line_id = getattr(vessel, "shipping_line_id", None)
        if vessel_line_id:
            recap_line_ids.add(int(vessel_line_id))
        if line_ids and vessel_line_id and vessel_line_id not in line_ids:
            unmatched.append(
                {
                    **base,
                    "reason": (
                        f"Barco «{vessel.name}» fuera de las navieras "
                        f"delimitadas del recap."
                    ),
                }
            )
            continue
        window_start = call_date - _DATE_WINDOW
        window_end = call_date + _DATE_WINDOW
        if date_from:
            window_start = max(window_start, date_from)
        if date_to:
            window_end = min(window_end, date_to)
        if window_start > window_end:
            unmatched.append(
                {
                    **base,
                    "reason": (
                        f"Sin reserva de {vessel.name} en {_port_label(port)} "
                        f"dentro del rango del recap."
                    ),
                }
            )
            continue
        # No status filter — cancelled bookings must match (ops recap decisions).
        candidates_qs = Booking.objects.filter(
            vessel_id=vessel.id,
            port_id=port.id,
            call_date__gte=window_start,
            call_date__lte=window_end,
        )
        if line_ids:
            candidates_qs = candidates_qs.filter(shipping_line_id__in=line_ids)
        elif effective_group_ids:
            candidates_qs = candidates_qs.filter(
                shipping_line__group_id__in=effective_group_ids
            )
        candidates = list(
            candidates_qs.select_related("vessel", "port", "shipping_line").order_by(
                "call_date", "id"
            )
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
        # Recap schedule for FE live re-score when the operator edits ETA/ETD/date.
        matches.append(
            {
                "booking_id": chosen.id,
                "booking_code": chosen.booking_code,
                "match": "exact" if not avisos else "approx",
                "match_percent": match_percent,
                "match_reason": match_reason,
                "avisos": avisos,
                "recap_call_date": (
                    call_date.isoformat() if isinstance(call_date, date) else None
                ),
                "recap_eta": (
                    _hhmm(row.get("eta"))
                    if isinstance(row.get("eta"), time)
                    else None
                ),
                "recap_etd": (
                    _hhmm(row.get("etd"))
                    if isinstance(row.get("etd"), time)
                    else None
                ),
            }
        )

    unmatched.sort(key=lambda item: item.get("row_number") or 0)
    portpax_only = find_portpax_only_bookings(
        date_from=date_from,
        date_to=date_to,
        recap_port_ids=recap_port_ids,
        recap_line_ids=recap_line_ids,
        matched_ids=used,
        shipping_line_ids=line_ids,
        shipping_line_group_ids=effective_group_ids,
        allowed_ports=allowed,
    )
    return {
        "imported_count": len(rows),
        "matched_count": len(matches),
        "matches": matches,
        "unmatched": unmatched,
        "portpax_only_count": len(portpax_only),
        "portpax_only": portpax_only,
    }
