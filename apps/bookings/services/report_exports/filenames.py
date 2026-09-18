"""Download filenames for ReportsView exports.

Rule: file name = managed report name (UI label) + extension.
"""

from __future__ import annotations

# Must match ReportsView tab labels / reportGuide names.
REPORT_MANAGED_NAMES: dict[str, str] = {
    "ports_totals_matrix": "Totals puertos",
    "port_carrier_matrix": "Totals por puerto",
    "port_trends": "Trends por puerto",
    "solicitudes_port": "Resumen de movimientos",
    "booking_movements": "Movimientos de bookings",
    "weekly_report": "Reporte Semanal",
    "availability": "Availability Chart",
}


def report_download_filename(report_type: str, ext: str) -> str:
    """``Totals puertos.xlsx``, ``Trends por puerto.pdf``, etc."""
    name = REPORT_MANAGED_NAMES.get(report_type) or report_type.replace("_", " ")
    clean_ext = (ext or "xlsx").lstrip(".").lower()
    return f"{name}.{clean_ext}"
