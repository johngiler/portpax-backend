from apps.bookings.services.arrivals_pdf.availability_pdf import (
    build_arrivals_availability_pdf,
)
from apps.bookings.services.arrivals_pdf.availability_xlsx import (
    build_arrivals_availability_xlsx,
)
from apps.bookings.services.arrivals_pdf.calendar_pdf import (
    build_arrivals_calendar_pdf,
)
from apps.bookings.services.arrivals_pdf.calendar_xlsx import (
    build_arrivals_calendar_xlsx,
)
from apps.bookings.services.arrivals_pdf.labels import (
    arrivals_range_title,
    arrivals_title,
)
from apps.bookings.services.arrivals_pdf.list_pdf import build_arrivals_list_pdf
from apps.bookings.services.arrivals_pdf.overview import build_overview
from apps.bookings.services.arrivals_pdf.proximity_pdf import (
    build_proximity_matrix_pdf,
)
from apps.bookings.services.arrivals_pdf.proximity_xlsx import (
    build_proximity_matrix_xlsx,
)

__all__ = [
    "arrivals_title",
    "arrivals_pdf_filename",
    "build_arrivals_availability_pdf",
    "build_arrivals_availability_xlsx",
    "build_arrivals_calendar_pdf",
    "build_arrivals_calendar_xlsx",
    "build_arrivals_list_pdf",
    "build_overview",
    "build_proximity_matrix_pdf",
    "build_proximity_matrix_xlsx",
]


def arrivals_pdf_filename(bookings: list, *, kind: str = "list") -> str:
    dates = [b.call_date for b in bookings]
    if kind == "list" and dates:
        title = arrivals_range_title(min(dates), max(dates))
        base = title.replace(" ", "_").replace("–", "-")
        return f"{base}.pdf"
    months = {(b.call_date.year, b.call_date.month) for b in bookings}
    if len(months) == 1:
        year, month = next(iter(months))
        base = arrivals_title(year, month).replace(" ", "_")
    else:
        base = "Arribos"
    if kind == "calendar":
        return f"{base}_calendario.pdf"
    if kind == "availability":
        return f"{base}_disponibilidad.pdf"
    return f"{base}.pdf"
