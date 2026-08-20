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
        ).select_related("vessel", "position", "position__port", "port")
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
    port=None,
) -> list[ValidationIssue]:
    """
    Single traffic-light aviso (green / yellow / red) with both vessels,
    positions, booking links, sum formula, and overhang when applicable.
    """
    from apps.bookings.services.validation.legend_labels import (
        port_legend_label,
        position_legend_label,
        vessel_legend_label,
    )

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

    port = (
        port
        or getattr(position, "port", None)
        or getattr(occupant, "port", None)
    )
    our_pos = position_legend_label(position, port=port)
    other_pos = position_legend_label(
        occupant.position if occupant.position_id else None,
        port=port,
    )
    our_ship = vessel_legend_label(vessel, fallback="Esta reserva")
    other_ship = vessel_legend_label(
        occupant.vessel if occupant.vessel_id else None,
        fallback="La otra escala",
    )
    port_label = port_legend_label(port)
    port_prefix = f"{port_label} · " if port_label else ""

    our_code = ""
    if exclude_booking_id:
        our_code = (
            Booking.objects.filter(pk=exclude_booking_id)
            .values_list("booking_code", flat=True)
            .first()
            or ""
        )

    sep = _decimal(rule.separation_m) or Decimal("0")
    combined = our_loa + other_loa + sep
    overhang = our_loa - remaining if our_loa > remaining else None

    # Stable E1 / E2 order in the legend.
    vessel_lines = sorted(
        [
            {
                "name": other_ship,
                "position": other_pos,
                "loa_m": str(other_loa),
                "booking_code": occupant.booking_code or "",
                "role": "sibling",
            },
            {
                "name": our_ship,
                "position": our_pos,
                "loa_m": str(our_loa),
                "booking_code": our_code,
                "role": "self",
            },
        ],
        key=lambda row: str(row["position"]),
    )
    line_bits = []
    for row in vessel_lines:
        bit = f"{row['name']} en {row['position']} ({row['loa_m']} m)"
        if row["booking_code"]:
            bit = f"{bit} · {row['booking_code']}"
        elif row["role"] == "self":
            bit = f"{bit} · esta reserva"
        line_bits.append(bit)

    sum_formula = (
        f"{our_ship} {our_loa} + {other_ship} {other_loa} + sep. {sep} "
        f"= {combined} m"
    )
    remaining_formula = (
        f"{rule.max_loa_m} − {other_ship} {other_loa} − sep. {sep} "
        f"= {remaining} m disponibles en {our_pos}"
    )

    yellow = _decimal(rule.yellow_from_m)
    red = _decimal(rule.red_from_m)
    if red is not None and combined >= red:
        code = "loa_recalc_sum_red"
        severity = "red"
        band = (
            f"Semáforo rojo: ocupación de muelle {combined} m "
            f"≥ {rule.red_from_m} m"
        )
    elif yellow is not None and combined >= yellow:
        code = "loa_recalc_sum_yellow"
        severity = "yellow"
        band = (
            f"Semáforo amarillo: ocupación de muelle {combined} m "
            f"entre {rule.yellow_from_m} y {rule.red_from_m} m"
        )
    elif overhang is not None:
        # Over pier max but under yellow band — still one yellow aviso with why.
        code = "loa_recalc_sum_yellow"
        severity = "yellow"
        band = (
            f"Semáforo amarillo: ocupación de muelle {combined} m "
            f"supera el máx. {rule.max_loa_m} m"
        )
    else:
        code = "loa_recalc_sum_green"
        severity = "green"
        band = (
            f"Semáforo verde: ocupación de muelle {combined} m "
            f"por debajo de {rule.yellow_from_m} m"
        )

    overhang_bit = ""
    if overhang is not None:
        overhang_bit = (
            f" Hueco en {our_pos}: {remaining} m → overhang {overhang} m "
            f"(máx. muelle {rule.max_loa_m} m)."
        )

    message = (
        f"{port_prefix}{band}. "
        f"{'; '.join(line_bits)}. "
        f"{sum_formula}.{overhang_bit}"
    )

    detail: dict = {
        "pier_max_m": str(rule.max_loa_m),
        "ship_loa_m": str(our_loa),
        "sibling_loa_m": str(other_loa),
        "separation_m": str(sep),
        "remaining_m": str(remaining),
        "sum_m": str(combined),
        "sibling_position": other_pos,
        "our_position": our_pos,
        "ship_name": our_ship,
        "sibling_vessel_name": other_ship,
        "sibling_booking_code": occupant.booking_code,
        "our_booking_code": our_code,
        "port_label": port_label,
        "vessel_lines": vessel_lines,
        "sum_formula": sum_formula,
        "formula": remaining_formula,
        "remaining_formula": remaining_formula,
    }
    if overhang is not None:
        detail["overhang_m"] = str(overhang)

    level = "info" if code == "loa_recalc_sum_green" else "warning"
    return [
        ValidationIssue(
            level,
            code,
            message.strip(),
            severity=severity,
            detail=detail,
        )
    ]
