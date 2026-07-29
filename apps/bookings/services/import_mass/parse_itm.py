"""Parse ITM mass-booking Excel (Ship, Port, Arrival, Departure, …)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from openpyxl import load_workbook

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
    if isinstance(value, str):
        text = value.strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


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
        for excel_row, row in enumerate(rows_iter, start=2):
            if row is None:
                continue
            values = list(row)
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
            raise ItmParseError("No se encontraron filas de reservas en el archivo.")
        return parsed
    finally:
        wb.close()
