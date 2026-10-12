"""Parse vessel size_category list filters for bookings API."""

from __future__ import annotations

from apps.bookings.constants import VESSEL_SIZE_CATEGORIES

_ALLOWED = frozenset(VESSEL_SIZE_CATEGORIES)


def parse_size_category_params(query_params) -> list[str]:
    """Accept repeated ?size_category= and comma lists. Order preserved, deduped."""
    raw_values = list(query_params.getlist("size_category"))
    if not raw_values:
        single = query_params.get("size_category")
        if single:
            raw_values = [single]

    parsed: list[str] = []
    seen: set[str] = set()
    for chunk in raw_values:
        for part in str(chunk).split(","):
            value = part.strip()
            if value in _ALLOWED and value not in seen:
                seen.add(value)
                parsed.append(value)
    return parsed
