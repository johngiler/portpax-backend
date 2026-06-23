from decimal import Decimal
from typing import Literal

from apps.bookings.constants import MAX_OVERHANG_M
from apps.bookings.models import Booking, BookingStatus
from apps.catalogs.models import Port, Position, Vessel


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
        status__in=[BookingStatus.REQUESTED, BookingStatus.CONFIRMED],
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
) -> list[ValidationIssue]:
    qs = Booking.objects.filter(
        position_id=position_id,
        call_date=call_date,
        status__in=[BookingStatus.REQUESTED, BookingStatus.CONFIRMED],
    )
    if exclude_booking_id:
        qs = qs.exclude(pk=exclude_booking_id)

    conflict = qs.select_related("vessel").first()
    if not conflict:
        return []

    return [
        ValidationIssue(
            "error",
            "position_occupied",
            f"La posición ya está asignada a {conflict.vessel.name} "
            f"({conflict.booking_code}).",
        )
    ]


def validate_booking(
    *,
    port: Port,
    vessel: Vessel,
    call_date,
    position: Position | None = None,
    exclude_booking_id: int | None = None,
) -> dict:
    issues: list[ValidationIssue] = []
    issues.extend(validate_multi_port_conflict(vessel.id, call_date, port.id, exclude_booking_id))
    if position:
        issues.extend(validate_position_availability(position.id, call_date, exclude_booking_id))
        issues.extend(validate_physical_fit(vessel, position, port))

    errors = [i.as_dict() for i in issues if i.level == "error"]
    warnings = [i.as_dict() for i in issues if i.level == "warning"]
    return {"errors": errors, "warnings": warnings, "valid": len(errors) == 0}
