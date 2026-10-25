"""Spanish date labels for arrivals flyers (lista / calendario)."""

from __future__ import annotations

from datetime import date, time

MONTHS_FULL = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
MONTHS_SHORT = (
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
# Monday = 0
WEEKDAYS_SHORT = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
# Sunday-first calendar headers (matches Costa Maya flyer + month grid UI)
WEEKDAYS_CAL = (
    "DOMINGO",
    "LUNES",
    "MARTES",
    "MIÉRCOLES",
    "JUEVES",
    "VIERNES",
    "SÁBADO",
)
WEEKDAYS_CAL_SHORT = ("DOM", "LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB")
# Monday-first week matrix (matches calendar weekly UI)
WEEKDAYS_WEEK_SHORT = ("LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM")

FOOTER_NOTE_LIST = "Calendario sujeto a cambios de último momento: actualizado"
FOOTER_NOTE_CAL = "Calendario sujeto a cambios de último momento, actualizado"
FOOTER_NOTE = FOOTER_NOTE_CAL


def month_title(year: int, month: int) -> str:
    return f"{MONTHS_FULL[month - 1]} {year}"


def arrivals_title(year: int, month: int) -> str:
    return f"Arribos {month_title(year, month)}"


def title_date_label(value: date) -> str:
    weekday = WEEKDAYS_SHORT[value.weekday()]
    weekday = weekday[:1].upper() + weekday[1:]
    return f"{weekday} {value.day} {MONTHS_SHORT[value.month - 1]} {value.year}"


def range_span_label(start: date, end: date) -> str:
    if start == end:
        return title_date_label(start)
    return f"{title_date_label(start)} – {title_date_label(end)}"


def arrivals_range_title(start: date, end: date) -> str:
    return f"Arribos {range_span_label(start, end)}"


AVAILABILITY_HEADING = "Disponibilidad de posiciones"


def availability_range_title(start: date, end: date) -> str:
    return f"{AVAILABILITY_HEADING} · {range_span_label(start, end)}"


def week_title(start: date, end: date) -> str:
    iso_week = start.isocalendar()[1]
    return f"Semana {iso_week} · {range_span_label(start, end)}"


def list_date_label(value: date) -> str:
    return (
        f"{WEEKDAYS_SHORT[value.weekday()]} "
        f"{value.day:02d}-{MONTHS_SHORT[value.month - 1]}-{value.year % 100:02d}"
    )


def updated_label(value: date) -> str:
    return f"{value.day:02d}-{MONTHS_FULL[value.month - 1]}-{value.year}"


def format_hhmm(value: time | None) -> str:
    if value is None:
        return ""
    return value.strftime("%H:%M")


def format_hhmm_short(value: time | None) -> str:
    """Calendar flyer times: 7:00 (no leading zero)."""
    if value is None:
        return ""
    return f"{value.hour}:{value.minute:02d}"


def sunday_first_pad(value: date) -> int:
    """Empty cells before day 1 when the week starts on Sunday."""
    return (value.weekday() + 1) % 7
