from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from django.db.models import Q

from apps.bookings.constants import (
    ACTIVE_BOOKING_STATUSES,
    ETA_CLOSE_GAP_HOURS,
    MAX_OVERHANG_M,
    OCCUPATION_CONFLICT_STATUSES,
)
from apps.bookings.models import Booking, BookingStatus
from apps.catalogs.models import Port, Position, PositionPairConstraint, Vessel

FULL_DAY_START = time(0, 0)
FULL_DAY_END = time(23, 59)


class ValidationIssue:
    def __init__(self, level: Literal["error", "warning"], code: str, message: str):
        self.level = level
        self.code = code
        self.message = message

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def occupation_window(eta: time | None, etd: time | None) -> tuple[time, time]:
    """Missing ETA/ETD → full-day occupation (00:00–23:59)."""
    return (eta or FULL_DAY_START, etd or FULL_DAY_END)


def times_overlap(
    eta_a: time | None,
    etd_a: time | None,
    eta_b: time | None,
    etd_b: time | None,
) -> bool:
    start_a, end_a = occupation_window(eta_a, etd_a)
    start_b, end_b = occupation_window(eta_b, etd_b)
    return start_a < end_b and end_a > start_b


def window_gap(
    eta_a: time | None,
    etd_a: time | None,
    eta_b: time | None,
    etd_b: time | None,
) -> timedelta | None:
    """Gap between non-overlapping windows; None if they overlap."""
    start_a, end_a = occupation_window(eta_a, etd_a)
    start_b, end_b = occupation_window(eta_b, etd_b)
    if start_a < end_b and end_a > start_b:
        return None
    day = datetime(2000, 1, 1)
    if end_a <= start_b:
        return datetime.combine(day.date(), start_b) - datetime.combine(day.date(), end_a)
    return datetime.combine(day.date(), start_a) - datetime.combine(day.date(), end_b)


def validate_physical_fit(
    vessel: Vessel,
    position: Position | None,
    port: Port,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not position:
        return issues

    loa = _decimal(vessel.loa_m)
    max_loa = _decimal(position.max_loa_m)
    if loa is not None and max_loa is not None:
        if loa > max_loa:
            over = loa - max_loa
            if over > MAX_OVERHANG_M:
                issues.append(
                    ValidationIssue(
                        "error",
                        "loa_exceeds_position",
                        f"LOA del barco ({loa} m) excede la posición {position.code} "
                        f"({max_loa} m) por más de {MAX_OVERHANG_M} m de overhang.",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        "warning",
                        "loa_overhang",
                        f"LOA ({loa} m) supera el máximo de {position.code} ({max_loa} m) "
                        f"con overhang de {over} m (límite {MAX_OVERHANG_M} m).",
                    )
                )

    beam = _decimal(vessel.beam_m)
    max_beam = _decimal(position.max_beam_m)
    if beam is not None and max_beam is not None and beam > max_beam:
        issues.append(
            ValidationIssue(
                "error",
                "beam_exceeds_position",
                f"Manga del barco ({beam} m) excede el máximo de {position.code} "
                f"({max_beam} m).",
            )
        )

    draft = _decimal(vessel.draft_m)
    depth_limits = [
        _decimal(position.min_draft_m),
        _decimal(position.berth.min_draft_m) if position.berth_id else None,
        _decimal(port.min_berth_draft_m),
    ]
    applicable = [d for d in depth_limits if d is not None]
    if draft is not None and applicable:
        min_depth = min(applicable)
        if draft > min_depth:
            issues.append(
                ValidationIssue(
                    "error",
                    "draft_too_deep",
                    f"Calado del barco ({draft} m) supera la profundidad disponible "
                    f"({min_depth} m) en {position.code}.",
                )
            )

    if vessel.pax_capacity is not None and position.bollard_count is not None:
        if vessel.mooring_line_count and vessel.mooring_line_count > position.bollard_count:
            issues.append(
                ValidationIssue(
                    "warning",
                    "mooring_capacity",
                    f"El barco requiere {vessel.mooring_line_count} líneas de amarre; "
                    f"{position.code} tiene {position.bollard_count} bitas.",
                )
            )

    return issues


def validate_multi_port_conflict(
    vessel_id: int,
    call_date,
    port_id: int,
    exclude_booking_id: int | None = None,
) -> list[ValidationIssue]:
    qs = Booking.objects.filter(
        vessel_id=vessel_id,
        call_date=call_date,
        status__in=ACTIVE_BOOKING_STATUSES,
    ).exclude(port_id=port_id)
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)

    other = qs.select_related("port").first()
    if not other:
        return []

    return [
        ValidationIssue(
            "warning",
            "multi_port_conflict",
            f"El mismo barco ya tiene escala en {other.port.name} "
            f"({other.booking_code}) en esta fecha.",
        )
    ]


def validate_position_availability(
    position_id: int,
    call_date,
    exclude_booking_id: int | None = None,
    *,
    eta: time | None = None,
    etd: time | None = None,
) -> list[ValidationIssue]:
    qs = Booking.objects.filter(
        position_id=position_id,
        call_date=call_date,
        status__in=OCCUPATION_CONFLICT_STATUSES,
    )
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)

    issues: list[ValidationIssue] = []
    for conflict in qs.select_related("vessel"):
        if times_overlap(eta, etd, conflict.eta, conflict.etd):
            if conflict.status == BookingStatus.CL:
                issues.append(
                    ValidationIssue(
                        "error",
                        "lta_priority_conflict",
                        f"La posición está ocupada por un call CL (LTA inamovible): "
                        f"{conflict.vessel.name} ({conflict.booking_code}).",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        "error",
                        "position_occupied",
                        f"La posición ya está asignada a {conflict.vessel.name} "
                        f"({conflict.booking_code}) en un horario solapado.",
                    )
                )
            continue

        gap = window_gap(eta, etd, conflict.eta, conflict.etd)
        if gap is not None and gap < timedelta(hours=ETA_CLOSE_GAP_HOURS):
            issues.append(
                ValidationIssue(
                    "warning",
                    "eta_close",
                    f"Menos de {ETA_CLOSE_GAP_HOURS} h entre esta escala y "
                    f"{conflict.vessel.name} ({conflict.booking_code}) en la misma posición.",
                )
            )

    return issues


def validate_min_eta(
    position: Position | None,
    eta: time | None,
) -> list[ValidationIssue]:
    if not position or not position.min_eta or eta is None:
        return []
    if eta < position.min_eta:
        return [
            ValidationIssue(
                "warning",
                "eta_before_min",
                f"ETA ({eta.strftime('%H:%M')}) es anterior al mínimo de "
                f"{position.code} ({position.min_eta.strftime('%H:%M')}).",
            )
        ]
    return []


def validate_combined_loa(
    vessel: Vessel,
    position: Position | None,
    call_date,
    exclude_booking_id: int | None = None,
) -> list[ValidationIssue]:
    if not position:
        return []

    constraints = PositionPairConstraint.objects.filter(
        port_id=position.port_id,
    ).filter(Q(position_a_id=position.id) | Q(position_b_id=position.id)).select_related(
        "position_a",
        "position_b",
    )

    issues: list[ValidationIssue] = []
    our_loa = _decimal(vessel.loa_m)
    if our_loa is None:
        return issues

    for constraint in constraints:
        other_id = (
            constraint.position_b_id
            if constraint.position_a_id == position.id
            else constraint.position_a_id
        )
        other_qs = Booking.objects.filter(
            position_id=other_id,
            call_date=call_date,
            status__in=OCCUPATION_CONFLICT_STATUSES,
        )
        if exclude_booking_id:
            other_qs = other_qs.exclude(pk=exclude_booking_id)
        other = other_qs.select_related("vessel", "position").first()
        if not other:
            continue

        other_loa = _decimal(other.vessel.loa_m)
        if other_loa is None:
            continue

        combined = our_loa + other_loa
        max_combined = _decimal(constraint.max_loa_combined)
        hard_cap = _decimal(constraint.max_loa_hard_cap)
        if max_combined is None or hard_cap is None:
            continue

        other_code = other.position.code if other.position_id else "?"
        if combined <= max_combined:
            continue
        if combined < hard_cap:
            issues.append(
                ValidationIssue(
                    "warning",
                    "combined_loa_orange",
                    f"LOA combinada ({combined} m) con {other_code} supera "
                    f"{max_combined} m pero está bajo el tope duro ({hard_cap} m).",
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    "error",
                    "combined_loa_red",
                    f"LOA combinada ({combined} m) con {other_code} alcanza o supera "
                    f"el tope duro ({hard_cap} m). Requiere autorización de port-operator.",
                )
            )

    return issues


def validate_booking(
    *,
    port: Port,
    vessel: Vessel,
    call_date,
    position: Position | None = None,
    eta: time | None = None,
    etd: time | None = None,
    exclude_booking_id: int | None = None,
    acknowledge_combined_red: bool = False,
) -> dict:
    issues: list[ValidationIssue] = []
    issues.extend(validate_multi_port_conflict(vessel.id, call_date, port.id, exclude_booking_id))
    if position:
        issues.extend(
            validate_position_availability(
                position.id,
                call_date,
                exclude_booking_id,
                eta=eta,
                etd=etd,
            )
        )
        issues.extend(validate_physical_fit(vessel, position, port))
        issues.extend(validate_min_eta(position, eta))
        issues.extend(validate_combined_loa(vessel, position, call_date, exclude_booking_id))

    if acknowledge_combined_red:
        for issue in issues:
            if issue.code == "combined_loa_red" and issue.level == "error":
                issue.level = "warning"

    errors = [i.as_dict() for i in issues if i.level == "error"]
    warnings = [i.as_dict() for i in issues if i.level == "warning"]
    return {"errors": errors, "warnings": warnings, "valid": len(errors) == 0}
