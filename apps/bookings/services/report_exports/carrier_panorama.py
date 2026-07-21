"""Carrier panorama — calls / PAX by port for one shipping line (no guarantees)."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from io import BytesIO, StringIO

from openpyxl import Workbook
from openpyxl.styles import Font

from apps.bookings.services.report_exports.common import (
    booking_pax,
    scheduled_bookings_qs,
    years_in_range,
)
from apps.catalogs.models import Port, ShippingLine


def build_carrier_panorama(
    *,
    shipping_line_id: int,
    date_from: date,
    date_to: date,
    allowed_ports: set[int] | None = None,
) -> dict:
    line = ShippingLine.objects.get(pk=shipping_line_id)
    qs = scheduled_bookings_qs(
        date_from=date_from,
        date_to=date_to,
        shipping_line_id=shipping_line_id,
        allowed_ports=allowed_ports,
    )

    # port_id -> year -> {calls, pax}
    by_port_year: dict[int, dict[int, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"calls": 0, "pax": 0})
    )
    port_ids_seen: set[int] = set()
    for b in qs.iterator(chunk_size=500):
        port_ids_seen.add(b.port_id)
        cell = by_port_year[b.port_id][b.call_date.year]
        cell["calls"] += 1
        cell["pax"] += booking_pax(b)

    years = years_in_range(date_from, date_to)
    ports = (
        list(Port.objects.filter(id__in=port_ids_seen).order_by("code"))
        if port_ids_seen
        else []
    )

    rows = []
    for port in ports:
        year_cells = []
        total_calls = 0
        total_pax = 0
        for y in years:
            c = by_port_year[port.id][y]
            year_cells.append({"year": y, "calls": c["calls"], "pax": c["pax"]})
            total_calls += c["calls"]
            total_pax += c["pax"]
        rows.append(
            {
                "port_id": port.id,
                "code": port.code,
                "name": port.name,
                "by_year": year_cells,
                "total_calls": total_calls,
                "total_pax": total_pax,
            }
        )

    return {
        "shipping_line": {
            "id": line.id,
            "code": line.code,
            "name": line.name,
        },
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "years": years,
        "ports": rows,
        "note": "Sin garantías contractuales (dato no modelado). PAX = actual o planificado.",
    }


def _carrier_panorama_table(data: dict) -> tuple[list, list[list]]:
    years = data["years"]
    header = ["Puerto", "Código"]
    for y in years:
        header.extend([f"{y} Calls", f"{y} Pax"])
    header.extend(["Total Calls", "Total Pax"])
    rows: list[list] = []
    for row in data["ports"]:
        out = [row["name"], row["code"]]
        for cell in row["by_year"]:
            out.extend([cell["calls"] or "", cell["pax"] or ""])
        out.extend([row["total_calls"] or "", row["total_pax"] or ""])
        rows.append(out)
    return header, rows


def build_carrier_panorama_xlsx(**kwargs) -> bytes:
    data = build_carrier_panorama(**kwargs)
    header, rows = _carrier_panorama_table(data)
    wb = Workbook()
    ws = wb.active
    ws.title = "Panorama"
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_carrier_panorama_csv(**kwargs) -> bytes:
    data = build_carrier_panorama(**kwargs)
    header, rows = _carrier_panorama_table(data)
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def carrier_panorama_filename(
    line_code: str,
    date_from: date,
    date_to: date,
    ext: str = "xlsx",
) -> str:
    safe = (line_code or "line").replace(" ", "_")
    return f"panorama_{safe}_{date_from.isoformat()}_{date_to.isoformat()}.{ext}"
