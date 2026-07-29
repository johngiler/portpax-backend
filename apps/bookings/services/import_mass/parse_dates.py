"""Flexible date/datetime parsing for mass-import pastes (ITM + availability)."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

# English months (full + abbr). Locale-independent.
_EN_MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

# Spanish months (full + abbr).
_ES_MONTHS: dict[str, int] = {
    "enero": 1,
    "ene": 1,
    "febrero": 2,
    "feb": 2,
    "marzo": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "julio": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "septiembre": 9,
    "setiembre": 9,
    "sep": 9,
    "sept": 9,
    "set": 9,
    "octubre": 10,
    "oct": 10,
    "noviembre": 11,
    "nov": 11,
    "diciembre": 12,
    "dic": 12,
}

_MONTHS: dict[str, int] = {**_EN_MONTHS, **_ES_MONTHS}

_WEEKDAY_PREFIX = re.compile(
    r"^(?:"
    # Full names (optional comma): Monday, 21 June 2027
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo"
    r")\s*,?\s+",
    re.IGNORECASE,
)

# Short weekday only with comma so «Mar 21, 2027» (March) is not stripped.
_WEEKDAY_SHORT_PREFIX = re.compile(
    r"^(?:"
    r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
    r"lun|mar|mi[eé]|jue|vie|s[aá]b|dom"
    r")\s*,\s+",
    re.IGNORECASE,
)

# 16-Feb-2028 8:00 | 16/Feb/2028 | 16 Feb 2028 08:00:00
_DAY_MON_YEAR = re.compile(
    r"^(\d{1,2})[\s\-/\.]+([A-Za-zÁÉÍÓÚáéíóúñÑ\.]+)[\s\-/\.]+(\d{2,4})"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)

# June 21, 2027 | Jun 21 2027 | junio 21, 2027
_MON_DAY_YEAR = re.compile(
    r"^([A-Za-zÁÉÍÓÚáéíóúñÑ\.]+)[\s\-/\.]+(\d{1,2}),?[\s\-/\.]+(\d{2,4})"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)

# 2027-06-16 / 2027/06/16 with optional time / T
_ISO_LIKE = re.compile(
    r"^(\d{4})[\-/\.](\d{1,2})[\-/\.](\d{1,2})"
    r"(?:[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)

# 16/06/2027 | 16-06-2027 | 16.06.2027 | 6/16/2027 (US) with optional time
_NUMERIC_DMY = re.compile(
    r"^(\d{1,2})[\-/\.](\d{1,2})[\-/\.](\d{2,4})"
    r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$"
)

_STRPTIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%d/%m/%y %H:%M",
    "%d/%m/%y",
    "%y-%m-%d",
)


def _month_number(token: str) -> int | None:
    key = token.strip().rstrip(".").lower()
    return _MONTHS.get(key)


def _normalize_year(year: int) -> int:
    if year < 100:
        return 2000 + year if year < 70 else 1900 + year
    return year


def _build_dt(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime | None:
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _normalize_text(text: str) -> str:
    cleaned = text.strip().replace("\u00a0", " ").replace("\u202f", " ")
    cleaned = cleaned.replace(",", ", ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _WEEKDAY_PREFIX.sub("", cleaned)
    cleaned = _WEEKDAY_SHORT_PREFIX.sub("", cleaned)
    # «16 de junio de 2027» → «16 junio 2027»
    cleaned = re.sub(r"\bde\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip(" ,;")
    return cleaned


def _from_day_mon_year(text: str) -> datetime | None:
    match = _DAY_MON_YEAR.match(text)
    if not match:
        return None
    day_s, mon_s, year_s, hh, mm, ss = match.groups()
    month = _month_number(mon_s)
    if month is None:
        return None
    return _build_dt(
        _normalize_year(int(year_s)),
        month,
        int(day_s),
        int(hh or 0),
        int(mm or 0),
        int(ss or 0),
    )


def _from_mon_day_year(text: str) -> datetime | None:
    match = _MON_DAY_YEAR.match(text)
    if not match:
        return None
    mon_s, day_s, year_s, hh, mm, ss = match.groups()
    month = _month_number(mon_s)
    if month is None:
        return None
    return _build_dt(
        _normalize_year(int(year_s)),
        month,
        int(day_s),
        int(hh or 0),
        int(mm or 0),
        int(ss or 0),
    )


def _from_iso_like(text: str) -> datetime | None:
    match = _ISO_LIKE.match(text)
    if not match:
        return None
    year_s, month_s, day_s, hh, mm, ss = match.groups()
    return _build_dt(
        int(year_s),
        int(month_s),
        int(day_s),
        int(hh or 0),
        int(mm or 0),
        int(ss or 0),
    )


def _from_numeric(text: str) -> datetime | None:
    """Parse d/m/y (preferred) or m/d/y when the first number is clearly a month."""
    match = _NUMERIC_DMY.match(text)
    if not match:
        return None
    a_s, b_s, year_s, hh, mm, ss = match.groups()
    a, b = int(a_s), int(b_s)
    year = _normalize_year(int(year_s))
    hour, minute, second = int(hh or 0), int(mm or 0), int(ss or 0)

    # Unambiguous: day > 12 → DMY; month-like first with day > 12 → MDY
    if a > 12 and b <= 12:
        return _build_dt(year, b, a, hour, minute, second)
    if b > 12 and a <= 12:
        return _build_dt(year, a, b, hour, minute, second)

    # Ambiguous (both ≤ 12): prefer DMY (LatAm / ITM ops).
    dmy = _build_dt(year, b, a, hour, minute, second)
    if dmy is not None:
        return dmy
    return _build_dt(year, a, b, hour, minute, second)


def _from_strptime(text: str) -> datetime | None:
    for fmt in _STRPTIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _from_excel_serial(value: float | int) -> datetime | None:
    # Excel 1900 date system (openpyxl / Windows).
    if isinstance(value, bool):
        return None
    serial = float(value)
    if serial < 20000 or serial > 80000:
        return None
    try:
        return datetime(1899, 12, 30) + timedelta(days=serial)
    except (OverflowError, ValueError):
        return None


def parse_flexible_datetime(value: Any) -> datetime | None:
    """
    Best-effort parse of pasted/Excel date-times.

    Accepts native date/datetime, Excel serials, and many string shapes:
    ISO, DMY/MDY, «16-Feb-2028 8:00», «Monday, 21 June 2027»,
    «16 de junio de 2027», etc.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _from_excel_serial(value)

    if not isinstance(value, str):
        return None

    text = _normalize_text(value)
    if not text:
        return None

    # Pure numeric string → Excel serial or YYYYMMDD
    if re.fullmatch(r"\d+(\.\d+)?", text):
        if "." in text or len(text) <= 5:
            return _from_excel_serial(float(text))
        if len(text) == 8:
            return _build_dt(int(text[:4]), int(text[4:6]), int(text[6:8]))

    for parser in (
        _from_iso_like,
        _from_day_mon_year,
        _from_mon_day_year,
        _from_numeric,
        _from_strptime,
    ):
        parsed = parser(text)
        if parsed is not None:
            return parsed

    # Last resort: drop trailing time zone / junk after year+time
    loosened = re.sub(r"\s*(UTC|GMT|Z|[+-]\d{2}:?\d{2})$", "", text, flags=re.I)
    if loosened != text:
        return parse_flexible_datetime(loosened)

    return None


def parse_flexible_date(value: Any) -> date | None:
    """Same as parse_flexible_datetime but returns a date (time discarded)."""
    parsed = parse_flexible_datetime(value)
    return parsed.date() if parsed else None


# Back-compat alias used by earlier ITM paste support.
def parse_day_mon_year_datetime(text: str) -> datetime | None:
    return parse_flexible_datetime(text)
