"""Shared pier LOA between two physical positions (recalc + traffic light)."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q

from apps.bookings.constants import OCCUPATION_CONFLICT_STATUSES
from apps.bookings.models import Booking
from apps.bookings.services.validation.rules import (
    ValidationIssue,
    _decimal,
    times_overlap,
)
from apps.catalogs.models import Position, PositionLoaRecalcRule


def remaining_shared_loa(
    *,
    max_loa: Decimal,
    occupant_loa: Decimal,
    separation: Decimal,
) -> Decimal:
    return max_loa - occupant_loa - separation


def _rules_for_position(position: Position):
    return (
        PositionLoaRecalcRule.objects.filter(is_active=True)
        .filter(Q(position_a_id=position.id) | Q(position_b_id=position.id))
        .select_related("position_a", "position_b")
    )


def pier_shared_max_loa(position: Position) -> Decimal | None:
    """Pier total max LOA from an active recalc rule, if any."""
    rule = _rules_for_position(position).first()
    if rule is None:
        return None
    return _decimal(rule.max_loa_m)


def sibling_occupant_for_recalc(
    position: Position,
    call_date,
    *,
    eta=None,
    etd=None,
    exclude_booking_id: int | None = None,
) -> tuple[PositionLoaRecalcRule, Booking, Decimal] | None:
    """
    If the paired sibling is occupied, return (rule, occupant, remaining_loa).
    """
    for rule in _rules_for_position(position):
        max_loa = _decimal(rule.max_loa_m)
        if max_loa is None:
            continue
        sibling_id = (
            rule.position_b_id
            if rule.position_a_id == position.id
            else rule.position_a_id
        )
        qs = Booking.objects.filter(
            position_id=sibling_id,
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
        occupant_loa = _decimal(occupant.vessel.loa_m)
        if occupant_loa is None:
            continue
        sep = _decimal(rule.separation_m) or Decimal("0")
        remaining = remaining_shared_loa(
            max_loa=max_loa,
            occupant_loa=occupant_loa,
            separation=sep,
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
    pier_max = pier_shared_max_loa(position)
    if pier_max is not None:
        return pier_max
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
    """
    Warnings only:
    - remaining sibling space exceeded (overhang on shared pier max)
    - traffic light on sum of both LOAs (green / yellow / red)
    """
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
    other_loa = _decimal(occupant.vessel.loa_m)
    if our_loa is None or other_loa is None:
        return []

    issues: list[ValidationIssue] = []
    other = occupant.position.code if occupant.position_id else "?"
    sep = _decimal(rule.separation_m) or Decimal("0")
    detail = {
        "pier_max_m": str(rule.max_loa_m),
        "ship_loa_m": str(our_loa),
        "sibling_loa_m": str(other_loa),
        "separation_m": str(sep),
        "remaining_m": str(remaining),
        "sum_m": str(our_loa + other_loa),
        "sibling_position": other,
        "sibling_booking_code": occupant.booking_code,
        "formula": (
            f"{rule.max_loa_m} − {other_loa} − {sep} = {remaining} m restantes "
            f"en {position.code}"
        ),
    }

    if our_loa > remaining:
        over = our_loa - remaining
        issues.append(
            ValidationIssue(
                "warning",
                "loa_recalc_exceeds",
                (
                    f"Recálculo de slora: máx. muelle {rule.max_loa_m} m − "
                    f"barco en {other} ({other_loa} m) − separación {sep} m "
                    f"= {remaining} m disponibles en {position.code}. "
                    f"Este barco mide {our_loa} m → overhang {over} m."
                ),
                severity="red",
                detail={**detail, "overhang_m": str(over)},
            )
        )

    combined = our_loa + other_loa
    yellow = _decimal(rule.yellow_from_m)
    red = _decimal(rule.red_from_m)
    if red is not None and combined >= red:
        issues.append(
            ValidationIssue(
                "warning",
                "loa_recalc_sum_red",
                (
                    f"Semáforo rojo: suma de esloras {combined} m "
                    f"({our_loa} + {other_loa} en {other}) ≥ {rule.red_from_m} m. "
                    f"{detail['formula']}."
                ),
                severity="red",
                detail=detail,
            )
        )
    elif yellow is not None and combined >= yellow:
        issues.append(
            ValidationIssue(
                "warning",
                "loa_recalc_sum_yellow",
                (
                    f"Semáforo amarillo: suma de esloras {combined} m "
                    f"({our_loa} + {other_loa} en {other}) entre "
                    f"{rule.yellow_from_m} y {rule.red_from_m} m. "
                    f"{detail['formula']}."
                ),
                severity="yellow",
                detail=detail,
            )
        )
    else:
        issues.append(
            ValidationIssue(
                "info",
                "loa_recalc_sum_green",
                (
                    f"Semáforo verde: suma de esloras {combined} m "
                    f"({our_loa} + {other_loa} en {other}) "
                    f"por debajo de {rule.yellow_from_m} m. "
                    f"{detail['formula']}."
                ),
                severity="green",
                detail=detail,
            )
        )

    return issues
