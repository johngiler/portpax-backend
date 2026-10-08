"""Parse mass-booking Excel or pasted TSV.

Canonical paste (homologated with booking recap):
  Group, Ship, Port, Arrival Date, ETA, ETD [, Assignment]

Legacy ITM still accepted:
  Ship, Port, Arrival, Departure [, Position…]
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from typing import Any, Iterable

from openpyxl import load_workbook

from apps.bookings.services.import_mass.parse_dates import parse_flexible_datetime

class ItmParseError(Exception):
    pass


_TIME_TEXT = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")

_GROUP = frozenset(
    {
        "group",
        "grupo",
        "naviera",
        "shipping line group",
        "shipping_line_group",
        "line group",
        "grupo de naviera",
    }
)
_SHIP = frozenset({"ship", "ship name", "barco", "vessel", "nombre del barco"})
_PORT = frozenset({"port", "port name", "puerto"})
_ARRIVAL_DATE_STRICT = frozenset(
    {
        "arrival date",
        "berth date",
        "call date",
        "fecha de escala",
    }
)
_ARRIVAL_DATE_LOOSE = frozenset({"fecha", "date"})
_ETA = frozenset({"eta", "arrive time", "hora llegada", "hora de llegada"})
_ETD = frozenset({"etd", "depart time", "hora salida", "hora de salida"})
_ASSIGNMENT = frozenset(
    {
        "assignment",
        "position",
        "posición",
        "posicion",
        "position code",
        "berth",
        "pos",
    }
)
_ARRIVAL = frozenset({"arrival", "llegada", "arrive"})
_DEPARTURE = frozenset({"departure", "salida", "depart"})


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def header_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def _index(headers: dict[str, int], names: frozenset[str]) -> int | None:
    for name in names:
        if name in headers:
            return headers[name]
    return None


def _as_time(value: Any) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, time):
        return value.replace(microsecond=0)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 0 <= float(value) < 1:
            seconds = int(round(float(value) * 24 * 3600))
            seconds %= 24 * 3600
            return time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)
        return None
    text = _cell_str(value)
    match = _TIME_TEXT.match(text)
    if not match:
        return None
    hour, minute, second = (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )
    if hour > 23 or minute > 59 or second > 59:
        return None
    return time(hour, minute, second)


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time(0, 0))
    return parse_flexible_datetime(value)


def _clock_from_datetime(value: datetime | None, *, explicit: bool) -> time | None:
    if value is None:
        return None
    clock = value.time().replace(microsecond=0)
    if not explicit and clock == time(0, 0):
        return None
    return clock


def _combine(day: date | None, clock: time | None) -> datetime | None:
    if day is None:
        return None
    return datetime.combine(day, clock or time(0, 0))


def _parse_itm_table(
    headers: list[str],
    body_rows: Iterable[tuple[int, list[Any]]],
) -> list[dict[str, Any]]:
    header_map = {header_key(h): i for i, h in enumerate(headers) if h}
    ship_i = _index(header_map, _SHIP)
    port_i = _index(header_map, _PORT)
    group_i = _index(header_map, _GROUP)
    date_strict_i = _index(header_map, _ARRIVAL_DATE_STRICT)
    date_loose_i = _index(header_map, _ARRIVAL_DATE_LOOSE)
    eta_i = _index(header_map, _ETA)
    etd_i = _index(header_map, _ETD)
    assignment_i = _index(header_map, _ASSIGNMENT)
    arrival_i = _index(header_map, _ARRIVAL)
    departure_i = _index(header_map, _DEPARTURE)
    vendor_i = header_map.get("vendor name")
    call_type_i = header_map.get("call type")

    # Prefer split date/time columns; bare Fecha/Date only when Arrival/Departure absent.
    date_i = date_strict_i
    if date_i is None and arrival_i is None:
        date_i = date_loose_i
    split_format = ship_i is not None and port_i is not None and date_i is not None
    legacy_format = (
        ship_i is not None
        and port_i is not None
        and arrival_i is not None
        and departure_i is not None
        and date_strict_i is None
    )
    if not split_format and not legacy_format:
        raise ItmParseError(
            "Faltan columnas. Formato: Group, Ship, Port, Arrival Date, ETA, ETD "
            "[, Assignment]. También se acepta el legacy Ship, Port, Arrival, Departure."
        )

    parsed: list[dict[str, Any]] = []
    for excel_row, values in body_rows:
        def cell(index: int | None) -> Any:
            if index is None or index >= len(values):
                return None
            return values[index]

        ship = _cell_str(cell(ship_i))
        port = _cell_str(cell(port_i))
        if not ship and not port:
            continue

        group_raw = _cell_str(cell(group_i)) if group_i is not None else ""
        vendor = (
            _cell_str(cell(vendor_i))
            if vendor_i is not None
            else ""
        )
        call_type = (
            _cell_str(cell(call_type_i))
            if call_type_i is not None
            else ""
        )
        position_raw = (
            _cell_str(cell(assignment_i))
            if assignment_i is not None
            else ""
        )

        if split_format:
            berth = _as_datetime(cell(date_i))
            call_day = berth.date() if berth is not None else None
            eta = _as_time(cell(eta_i)) if eta_i is not None else None
            etd = _as_time(cell(etd_i)) if etd_i is not None else None
            # Legacy remap may put a full datetime in Arrival Date / ETD cells.
            if eta is None and berth is not None:
                eta = _clock_from_datetime(berth, explicit=False)
            if etd is None and etd_i is not None:
                etd_dt = _as_datetime(cell(etd_i))
                etd = _clock_from_datetime(etd_dt, explicit=False)
                if call_day is None and etd_dt is not None:
                    call_day = etd_dt.date()
            arrival = _combine(call_day, eta)
            departure = _combine(call_day, etd)
        else:
            arrival = _as_datetime(cell(arrival_i))
            departure = _as_datetime(cell(departure_i))

        parsed.append(
            {
                "row_number": excel_row,
                "ship": ship,
                "port_raw": port,
                "group_raw": group_raw,
                "arrival": arrival,
                "departure": departure,
                "vendor_name": vendor or group_raw,
                "call_type": call_type,
                "position_raw": position_raw,
            }
        )

    if not parsed:
        raise ItmParseError("No se encontraron filas de reservas.")
    return parsed


def parse_itm_workbook(file_obj) -> list[dict[str, Any]]:
    """Return raw rows from the first sheet of an ITM-format xlsx."""
    wb = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration as exc:
            raise ItmParseError("El archivo está vacío.") from exc

        headers = [_cell_str(h) for h in (header or ())]
        body: list[tuple[int, list[Any]]] = []
        for excel_row, row in enumerate(rows_iter, start=2):
            if row is None:
                continue
            body.append((excel_row, list(row)))
        return _parse_itm_table(headers, body)
    finally:
        wb.close()


def parse_itm_tsv(text: str) -> list[dict[str, Any]]:
    """Parse clipboard paste from Excel/Sheets/email as ITM columns."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ItmParseError(
            "Pega al menos una fila con Group, Ship, Port, Arrival Date, ETA y ETD."
        )

    lines = [ln for ln in raw.split("\n") if ln.strip()]
    if not lines:
        raise ItmParseError(
            "Pega al menos una fila con Group, Ship, Port, Arrival Date, ETA y ETD."
        )

    vertical = _reshape_vertical_itm_lines(lines)
    if vertical is not None:
        headers, body_rows = vertical
        body = [(i, row) for i, row in enumerate(body_rows, start=2)]
        return _parse_itm_table(headers, body)

    def split_line(line: str) -> list[str]:
        if "\t" in line:
            return [_cell_str(c) for c in line.split("\t")]
        if ";" in line:
            return [_cell_str(c) for c in line.split(";")]
        return [_cell_str(line)]

    headers = split_line(lines[0])
    body = [(i, split_line(line)) for i, line in enumerate(lines[1:], start=2)]
    if not body:
        raise ItmParseError(
            "Incluye la fila de encabezados (Group, Ship, Port, Arrival Date, ETA, ETD) "
            "y al menos una fila de datos."
        )
    return _parse_itm_table(headers, body)


_VERTICAL_ITM_HEADERS = (
    "Group",
    "Ship",
    "Port",
    "Arrival Date",
    "ETA",
    "ETD",
    "Assignment",
    "Arrival",
    "Departure",
    "Vendor Name",
    "Call Type",
    "Position",
)
_VERTICAL_ITM_KEYS = {h.lower(): h for h in _VERTICAL_ITM_HEADERS}
_VERTICAL_ITM_KEYS.update(
    {
        "grupo": "Group",
        "naviera": "Group",
        "shipping line group": "Group",
        "arrival date": "Arrival Date",
        "berth date": "Arrival Date",
        "fecha": "Arrival Date",
        "arrive time": "ETA",
        "depart time": "ETD",
        "posición": "Assignment",
        "posicion": "Assignment",
        "position code": "Assignment",
        "assignment": "Assignment",
        "berth": "Assignment",
        "pos": "Assignment",
        "position": "Assignment",
    }
)


def _reshape_vertical_itm_lines(
    lines: list[str],
) -> tuple[list[str], list[list[str]]] | None:
    """
    Outlook/email often copies ITM tables as one field per line:
    headers, then repeating value blocks of the same width.
    """
    trimmed = [_cell_str(ln) for ln in lines if _cell_str(ln)]
    if len(trimmed) < 8:
        return None

    mostly_single = (
        sum(1 for ln in trimmed if "\t" not in ln and ";" not in ln)
        >= len(trimmed) * 0.85
    )
    if not mostly_single:
        return None

    headers: list[str] = []
    for line in trimmed:
        key = header_key(line)
        if key not in _VERTICAL_ITM_KEYS:
            break
        headers.append(_VERTICAL_ITM_KEYS[key])

    if len(headers) < 4:
        return None
    header_keys = {header_key(h) for h in headers}
    has_split = "arrival date" in header_keys or "berth date" in header_keys
    has_legacy = "arrival" in header_keys and "departure" in header_keys
    if "ship" not in header_keys or "port" not in header_keys:
        return None
    if not has_split and not has_legacy:
        return None

    width = len(headers)
    data = trimmed[len(headers) :]
    if len(data) < width or len(data) % width != 0:
        return None

    body = [data[i : i + width] for i in range(0, len(data), width)]
    return headers, body
