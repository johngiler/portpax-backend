"""LTA matching helpers (horizon grant + slot ownership)."""

from __future__ import annotations

import calendar
from datetime import date

from django.db.models import QuerySet

from apps.bookings.models import LongTermAgreement
from apps.catalogs.models import Position, Vessel

DEFAULT_ADVANCE_MONTHS_MIN = 18
DEFAULT_ADVANCE_MONTHS_MAX = 32


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _base_qs() -> QuerySet[LongTermAgreement]:
    return LongTermAgreement.objects.filter(is_active=True).select_related(
        "port",
        "shipping_line",
    ).prefetch_related("vessels", "positions")


def agreement_covers_validity(agreement: LongTermAgreement, call_date: date) -> bool:
    if agreement.valid_from and call_date < agreement.valid_from:
        return False
    if agreement.valid_until and call_date > agreement.valid_until:
        return False
    return True


def agreement_covers_weekday(agreement: LongTermAgreement, call_date: date) -> bool:
    weekdays = agreement.weekdays or []
    if not weekdays:
        return True
    return call_date.weekday() in weekdays


def agreement_covers_cadence(agreement: LongTermAgreement, call_date: date) -> bool:
    """When interval_days + cadence_anchor are set, call_date must land on the grid."""
    interval = agreement.interval_days
    anchor = agreement.cadence_anchor
    if not interval or anchor is None:
        return True
    delta = (call_date - anchor).days
    if delta < 0:
        return False
    return delta % interval == 0


def agreement_covers_vessel(agreement: LongTermAgreement, vessel: Vessel) -> bool:
    if agreement.all_vessels:
        return vessel.shipping_line_id == agreement.shipping_line_id
    vessel_ids = {v.id for v in agreement.vessels.all()}
    return vessel.id in vessel_ids


def agreement_covers_position(
    agreement: LongTermAgreement,
    position: Position | None,
    *,
    require_position: bool,
) -> bool:
    position_ids = {p.id for p in agreement.positions.all()}
    if not position_ids:
        # No positions configured = whole port (horizon only; slot rules skip).
        return not require_position
    if position is None:
        return not require_position
    return position.id in position_ids


def find_matching_agreements(
    *,
    port_id: int,
    shipping_line_id: int,
    vessel: Vessel,
    call_date: date,
    position: Position | None = None,
    require_position: bool = False,
) -> list[LongTermAgreement]:
    """Own-line LTAs that cover vessel/weekday/(optional position) on call_date."""
    matches: list[LongTermAgreement] = []
    qs = _base_qs().filter(port_id=port_id, shipping_line_id=shipping_line_id)
    for agreement in qs:
        if not agreement_covers_validity(agreement, call_date):
            continue
        if not agreement_covers_weekday(agreement, call_date):
            continue
        if not agreement_covers_cadence(agreement, call_date):
            continue
        if not agreement_covers_vessel(agreement, vessel):
            continue
        if not agreement_covers_position(
            agreement,
            position,
            require_position=require_position,
        ):
            continue
        matches.append(agreement)
    return matches


def find_best_matching_agreement(
    *,
    port_id: int,
    shipping_line_id: int,
    vessel: Vessel,
    call_date: date,
    position: Position | None = None,
) -> LongTermAgreement | None:
    matches = find_matching_agreements(
        port_id=port_id,
        shipping_line_id=shipping_line_id,
        vessel=vessel,
        call_date=call_date,
        position=position,
        require_position=False,
    )
    if not matches:
        return None
    # Prefer agreements that explicitly list the position when present.
    if position is not None:
        with_pos = [
            a
            for a in matches
            if agreement_covers_position(a, position, require_position=True)
        ]
        if with_pos:
            matches = with_pos
    matches.sort(key=lambda a: (a.advance_months_max, a.code))
    return matches[0]


def find_foreign_slot_agreements(
    *,
    port_id: int,
    shipping_line_id: int,
    call_date: date,
    position: Position | None,
) -> list[LongTermAgreement]:
    """Other lines' LTAs that strategically own this weekday + position."""
    if position is None:
        return []
    qs = (
        _base_qs()
        .filter(port_id=port_id)
        .exclude(shipping_line_id=shipping_line_id)
        .filter(positions=position)
    )
    foreign: list[LongTermAgreement] = []
    for agreement in qs.distinct():
        if not agreement_covers_validity(agreement, call_date):
            continue
        if not agreement_covers_weekday(agreement, call_date):
            continue
        foreign.append(agreement)
    return foreign


def system_far_window(
    today: date | None = None,
) -> tuple[date, date]:
    """Default strategic window [today+18m, today+32m]."""
    today = today or date.today()
    return (
        add_months(today, DEFAULT_ADVANCE_MONTHS_MIN),
        add_months(today, DEFAULT_ADVANCE_MONTHS_MAX),
    )
