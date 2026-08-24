"""Parse discrete call_date lists from API query params."""

from __future__ import annotations

from datetime import date

from django.utils.dateparse import parse_date

# Cap keeps URL/query size bounded (imported availability lists).
MAX_CALL_DATES = 400


def parse_call_dates_param(raw: str | None) -> list[date]:
    """Comma-separated ISO dates → unique sorted list (empty if none/invalid)."""
    if raw is None or str(raw).strip() == "":
        return []
    seen: set[date] = set()
    out: list[date] = []
    for part in str(raw).split(","):
        token = part.strip()
        if not token:
            continue
        parsed = parse_date(token)
        if parsed is None:
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        out.append(parsed)
        if len(out) >= MAX_CALL_DATES:
            break
    out.sort()
    return out
