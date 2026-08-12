"""Shared remaining-LOA when a non-mega ship occupies one combined component."""

from __future__ import annotations

from decimal import Decimal

from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
from apps.bookings.models import Booking
from apps.bookings.services.validation.rules import (
    ValidationIssue,
    _decimal,
    times_overlap,
    vessel_meets_combined_min,
)
from apps.catalogs.models import Position, PositionComponent, PositionLoaRecalcRule


def remaining_shared_loa(
    *,
    combined_max: Decimal,
    occupant_loa: Decimal,
    min_separation: Decimal,
) -> Decimal:
    return combined_max - occupant_loa - min_separation


def sibling_occupant_for_recalc(
    position: Position,
    call_date,
    *,
    eta=None,
    etd=None,
    exclude_booking_id: int | None = None,
) -> tuple[PositionLoaRecalcRule, Booking, Decimal] | None:
    """
    If a non-mega sibling occupies the other component, return
    (rule, occupant, remaining_loa).
    """
    component_ids = set(
        PositionComponent.objects.filter(
            source_position_id=position.id,
        ).values_list("combined_position_id", flat=True)
    )
    if not component_ids:
        return None

    rules = (
        PositionLoaRecalcRule.objects.filter(
            combined_position_id__in=component_ids,
            is_active=True,
        )
        .select_related("combined_position")
        .prefetch_related("combined_position__component_links")
    )
    for rule in rules:
        combined = rule.combined_position
        combined_max = _decimal(combined.max_loa_m)
        if combined_max is None:
            continue
        sibling_ids = [
            link.source_position_id
            for link in combined.component_links.all()
            if link.source_position_id != position.id
        ]
        if not sibling_ids:
            continue
        qs = Booking.objects.filter(
            position_id__in=sibling_ids,
            call_date=call_date,
            status__in=OCCUPATION_CONFLICT_STATUSES,
        ).select_related("vessel", "position")
        if exclude_booking_id:
            qs = qs.exclude(pk=exclude_booking_id)
        occupant = qs.order_by("id").first()
        if occupant is None:
            continue
        if not times_overlap(eta, etd, occupant.eta, occupant.etd):
            continue
        if vessel_meets_combined_min(occupant.vessel, combined.min_loa_m):
            continue
        occupant_loa = _decimal(occupant.vessel.loa_m)
        if occupant_loa is None:
            continue
        sep = _decimal(rule.min_separation_m) or Decimal("0")
        remaining = remaining_shared_loa(
            combined_max=combined_max,
            occupant_loa=occupant_loa,
            min_separation=sep,
        )
        return rule, occupant, remaining
    return None


def effective_max_loa_m(
    position: Position,
    call_date,
    *,
    eta=None,
    etd=None,
    exclude_booking_id: int | None = None,
) -> Decimal | None:
    found = sibling_occupant_for_recalc(
        position,
        call_date,
        eta=eta,
        etd=etd,
        exclude_booking_id=exclude_booking_id,
    )
    if found is not None:
        return found[2]
    return _decimal(position.max_loa_m)


def validate_loa_recalc(
    vessel,
    position: Position | None,
    call_date,
    *,
    eta=None,
    etd=None,
    exclude_booking_id: int | None = None,
) -> list[ValidationIssue]:
    if not position:
        return []
    found = sibling_occupant_for_recalc(
        position,
        call_date,
        eta=eta,
        etd=etd,
        exclude_booking_id=exclude_booking_id,
    )
    if found is None:
        return []
    rule, occupant, remaining = found
    our_loa = _decimal(vessel.loa_m)
    if our_loa is None:
        return []
    if our_loa <= remaining:
        return []
    other = occupant.position.code if occupant.position_id else "?"
    return [
        ValidationIssue(
            "warning",
            "loa_recalc_exceeds",
            f"Eslora restante en {position.code}: {remaining} m "
            f"({rule.combined_position.code} {rule.combined_position.max_loa_m} m "
            f"− {occupant.vessel.loa_m} m en {other} "
            f"− {rule.min_separation_m} m de separación). "
            f"El barco mide {our_loa} m.",
        )
    ]
