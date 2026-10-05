"""Parse a booking recap sheet (Ship, Port, date, arrive/depart — no position)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from typing import Any, Iterable

from openpyxl import load_workbook

from apps.bookings.services.import_mass.parse_dates import parse_flexible_datetime
from apps.bookings.services.import_mass.parse_itm import ItmParseError

_SHIP = frozenset({"ship", "ship name", "barco", "vessel", "nombre del barco"})
_PORT = frozenset({"port", "port name", "puerto"})
_BERTH_DATE = frozenset(
    {"berth date", "fecha", "call date", "fecha de escala", "date"}
)
_ARRIVAL = frozenset({"arrival", "llegada", "arrive"})
_DEPARTURE = frozenset({"departure", "salida", "depart"})
_ARRIVE_TIME = frozenset(
    {"arrive time", "eta", "hora llegada", "hora de llegada"}
)
_DEPART_TIME = frozenset(
    {"depart time", "etd", "hora salida", "hora de salida"}
)
_TIME_TEXT = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _header_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


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
    hour, minute, second = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    return time(hour, minute, second)


def _clock_from_datetime(value: datetime | None, *, explicit: bool) -> time | None:
    """Date-only cells land at midnight; keep 00:00 only when the column is a time."""
    if value is None:
        return None
    clock = value.time().replace(microsecond=0)
    if not explicit and clock == time(0, 0):
        return None
    return clock


def _index(headers: dict[str, int], names: frozenset[str]) -> int | None:
    for name in names:
        if name in headers:
            return headers[name]
    return None


def _parse_table(
    headers: list[str],
    body_rows: Iterable[tuple[int, list[Any]]],
) -> list[dict[str, Any]]:
    header_map = {_header_key(h): i for i, h in enumerate(headers) if h}
    ship_i = _index(header_map, _SHIP)
    port_i = _index(header_map, _PORT)
    date_i = _index(header_map, _BERTH_DATE)
    arrival_i = _index(header_map, _ARRIVAL)
    departure_i = _index(header_map, _DEPARTURE)
    eta_i = _index(header_map, _ARRIVE_TIME)
    etd_i = _index(header_map, _DEPART_TIME)
    if ship_i is None or port_i is None or (date_i is None and arrival_i is None):
        raise ItmParseError(
            "Faltan columnas. Usa Ship, Port y Berth Date "
            "(o Arrival / Departure), sin posición."
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

        berth = parse_flexible_datetime(cell(date_i)) if date_i is not None else None
        arrival = parse_flexible_datetime(cell(arrival_i)) if arrival_i is not None else None
        departure = (
            parse_flexible_datetime(cell(departure_i)) if departure_i is not None else None
        )
        call_dt = berth or arrival
        if call_dt is None:
            parsed.append(
                {
                    "row_number": excel_row,
                    "ship": ship,
                    "port_raw": port,
                    "call_date": None,
                    "eta": None,
                    "etd": None,
                }
            )
            continue

        eta = _as_time(cell(eta_i)) if eta_i is not None else None
        etd = _as_time(cell(etd_i)) if etd_i is not None else None
        if eta is None:
            eta = _clock_from_datetime(arrival, explicit=False)
        if etd is None:
            etd = _clock_from_datetime(departure, explicit=False)

        parsed.append(
            {
                "row_number": excel_row,
                "ship": ship,
                "port_raw": port,
                "call_date": call_dt.date(),
                "eta": eta,
                "etd": etd,
            }
        )

    if not parsed:
        raise ItmParseError("No se encontraron filas de recap.")
    return parsed


def parse_recap_workbook(file_obj) -> list[dict[str, Any]]:
    wb = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration as exc:
            raise ItmParseError("El archivo está vacío.") from exc
        headers = [_cell_str(h) for h in (header or ())]
        body = [
            (excel_row, list(row or ()))
            for excel_row, row in enumerate(rows_iter, start=2)
            if row is not None
        ]
        return _parse_table(headers, body)
    finally:
        wb.close()


def parse_recap_tsv(text: str) -> list[dict[str, Any]]:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ItmParseError(
            "Pega al menos una fila con Ship, Port y Berth Date."
        )
    lines = [ln for ln in raw.split("\n") if ln.strip()]

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
            "Incluye la fila de encabezados y al menos una fila de datos."
        )
    return _parse_table(headers, body)
