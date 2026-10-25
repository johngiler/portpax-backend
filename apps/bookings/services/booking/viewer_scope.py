"""Solo lectura: bookings in current + open-booking blocks only."""

from __future__ import annotations

from datetime import date

from apps.accounts.models import UserRole
from apps.accounts.permissions import user_role
from apps.bookings.services.lta.windows import compute_seasonal_windows


def viewer_open_market_bounds(today: date | None = None) -> tuple[date, date]:
    """Inclusive call-date window: período actual + 3 bloques open booking."""
    windows = compute_seasonal_windows(today)
    return windows.current_from, windows.general_to


def clamp_viewer_open_market_range(
    user,
    date_from: date | None,
    date_to: date | None,
    *,
    today: date | None = None,
) -> tuple[date | None, date | None]:
    """Intersect a requested range with the viewer open-market window."""
    if date_from is None or date_to is None:
        return date_from, date_to
    if user_role(user) != UserRole.VIEWER:
        return date_from, date_to
    start, end = viewer_open_market_bounds(today)
    return max(date_from, start), min(date_to, end)


def apply_viewer_open_market_filter(qs, user, *, field: str = "call_date"):
    """Hide LTA-zone (and older) bookings from the viewer role."""
    if user_role(user) != UserRole.VIEWER:
        return qs
    start, end = viewer_open_market_bounds()
    return qs.filter(**{f"{field}__gte": start, f"{field}__lte": end})
