"""Parse ITM mass-booking Excel or pasted TSV (Ship, Port, Arrival, Departure, …)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Iterable

from openpyxl import load_workbook

from apps.bookings.services.import_mass.parse_dates import parse_flexible_datetime

REQUIRED_HEADERS = ("Ship", "Port", "Arrival", "Departure")


class ItmParseError(Exception):
    pass


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time(0, 0))
    return parse_flexible_datetime(value)


def _parse_itm_table(
    headers: list[str],
    body_rows: Iterable[tuple[int, list[Any]]],
) -> list[dict[str, Any]]:
    lower_map = {h.lower(): i for i, h in enumerate(headers) if h}
    for required in REQUIRED_HEADERS:
        if required.lower() not in lower_map:
            raise ItmParseError(
                f"Falta la columna «{required}». "
                "Formato esperado: Ship, Port, Arrival, Departure, …"
            )

    ship_i = lower_map["ship"]
    port_i = lower_map["port"]
    arr_i = lower_map["arrival"]
    dep_i = lower_map["departure"]
    vendor_i = lower_map.get("vendor name")
    call_type_i = lower_map.get("call type")

    parsed: list[dict[str, Any]] = []
    for excel_row, values in body_rows:
        ship = _cell_str(values[ship_i] if ship_i < len(values) else None)
        port = _cell_str(values[port_i] if port_i < len(values) else None)
        if not ship and not port:
            continue

        arrival = _as_datetime(values[arr_i] if arr_i < len(values) else None)
        departure = _as_datetime(values[dep_i] if dep_i < len(values) else None)
        vendor = (
            _cell_str(values[vendor_i] if vendor_i is not None and vendor_i < len(values) else None)
            if vendor_i is not None
            else ""
        )
        call_type = (
            _cell_str(
                values[call_type_i]
                if call_type_i is not None and call_type_i < len(values)
                else None
            )
            if call_type_i is not None
            else ""
        )

        parsed.append(
            {
                "row_number": excel_row,
                "ship": ship,
                "port_raw": port,
                "arrival": arrival,
                "departure": departure,
                "vendor_name": vendor,
                "call_type": call_type,
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
    """Parse clipboard paste from Excel/Sheets as ITM columns (TSV)."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ItmParseError(
            "Pega al menos una fila con Ship, Port, Arrival y Departure."
        )

    lines = [ln for ln in raw.split("\n") if ln.strip()]
    if not lines:
        raise ItmParseError(
            "Pega al menos una fila con Ship, Port, Arrival y Departure."
        )

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
            "Incluye la fila de encabezados (Ship, Port, Arrival, Departure) "
            "y al menos una fila de datos."
        )
    return _parse_itm_table(headers, body)
