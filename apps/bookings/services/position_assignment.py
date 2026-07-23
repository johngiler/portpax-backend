from datetime import date
from decimal import Decimal

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.validation.rules import (
    ValidationIssue,
    validate_physical_fit,
    validate_position_availability,
    _decimal,
)
from apps.catalogs.models import Port, Position, Vessel


def _rank_position(vessel: Vessel, position: Position, port: Port) -> tuple:
    """Lower tuple wins. First-in: sort_order before tighter LOA fit."""
    physical = validate_physical_fit(vessel, position, port)
    has_overhang = 1 if any(i.code == "loa_overhang" for i in physical) else 0

    loa = _decimal(vessel.loa_m)
    max_loa = _decimal(position.max_loa_m)
    loa_slack = Decimal("999999")
    if loa is not None and max_loa is not None:
        loa_slack = abs(max_loa - loa)

    return (position.sort_order, has_overhang, loa_slack, position.code)


def auto_assign_position(
    port: Port,
    vessel: Vessel,
    call_date: date,
    *,
    exclude_booking_id: int | None = None,
    reserved_position_ids: set[int] | None = None,
) -> Position | None:
    """
    Pick the best pier slot for vessel dimensions on call_date.

    First-in order (sort_order / P1 before P2), then physical fit without errors.
    Skips occupied slots and slots reserved in the same batch transaction.
    """
    reserved = reserved_position_ids or set()

    positions = Position.objects.filter(
        port_id=port.id,
        is_active=True,
    ).select_related("berth").order_by("sort_order", "code")

    candidates: list[tuple[tuple, Position]] = []

    for position in positions:
        if position.id in reserved:
            continue

        physical_issues = validate_physical_fit(vessel, position, port)
        if any(issue.level == "error" for issue in physical_issues):
            continue

        occupancy_issues = validate_position_availability(
            position.id,
            call_date,
            exclude_booking_id,
        )
        if any(issue.level == "error" for issue in occupancy_issues):
            continue

        candidates.append((_rank_position(vessel, position, port), position))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def try_preferred_position(
    port: Port,
    vessel: Vessel,
    call_date: date,
    preferred_position_id: int,
    *,
    exclude_booking_id: int | None = None,
    reserved_position_ids: set[int] | None = None,
) -> Position | None:
    """Return preferred pier if free and physically fit; otherwise None."""
    reserved = reserved_position_ids or set()
    if preferred_position_id in reserved:
        return None
    try:
        position = Position.objects.select_related("berth").get(
            pk=preferred_position_id,
            port_id=port.id,
            is_active=True,
        )
    except Position.DoesNotExist:
        return None

    physical_issues = validate_physical_fit(vessel, position, port)
    if any(issue.level == "error" for issue in physical_issues):
        return None

    occupancy_issues = validate_position_availability(
        position.id,
        call_date,
        exclude_booking_id,
    )
    if any(issue.level == "error" for issue in occupancy_issues):
        return None

    return position


def resolve_booking_position(
    port: Port,
    vessel: Vessel,
    call_date: date,
    *,
    preferred_position_id: int | None = None,
    exclude_booking_id: int | None = None,
    reserved_position_ids: set[int] | None = None,
) -> Position | None:
    if preferred_position_id:
        preferred = try_preferred_position(
            port,
            vessel,
            call_date,
            preferred_position_id,
            exclude_booking_id=exclude_booking_id,
            reserved_position_ids=reserved_position_ids,
        )
        if preferred:
            return preferred
    return auto_assign_position(
        port,
        vessel,
        call_date,
        exclude_booking_id=exclude_booking_id,
        reserved_position_ids=reserved_position_ids,
    )


def no_position_available_warning(
    port: Port,
    vessel: Vessel,
    call_date: date,
) -> ValidationIssue | None:
    if auto_assign_position(port, vessel, call_date):
        return None

    loa = vessel.loa_m
    draft = vessel.draft_m
    dims = []
    if loa is not None:
        dims.append(f"LOA {loa} m")
    if draft is not None:
        dims.append(f"calado {draft} m")
    dim_text = f" ({', '.join(dims)})" if dims else ""

    return ValidationIssue(
        "warning",
        "no_position_available",
        f"No hay posición libre que cumpla dimensiones{dim_text} "
        f"para {call_date.isoformat()} en {port.name}.",
    )
