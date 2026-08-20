from datetime import date
from decimal import Decimal

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.validation.rules import (
    ValidationIssue,
    related_position_ids,
    validate_physical_fit,
    validate_position_availability,
    _decimal,
)
from apps.catalogs.models import Port, Position, Vessel
from apps.catalogs.services.position_combination import (
    exclude_combined_positions,
    position_is_combined,
)


def _rank_position(vessel: Vessel, position: Position, port: Port) -> tuple:
    """Lower tuple wins: catalog order, then LOA slack, then overhang."""
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

    Prefers free physical piers with fewer conflicts; combined slots excluded.
    Operational conflicts are non-blocking (caller persists has_conflict).
    """
    from apps.bookings.services.validation.loa_recalc import validate_loa_recalc

    reserved = reserved_position_ids or set()

    positions = exclude_combined_positions(
        Position.objects.filter(
            port_id=port.id,
            is_active=True,
        )
        .select_related("berth")
        .prefetch_related("component_links")
        .order_by("sort_order", "code")
    )

    candidates: list[tuple[tuple, Position]] = []

    for position in positions:
        if position_is_combined(position):
            continue
        if reserved & related_position_ids(position.id):
            continue

        physical_issues = validate_physical_fit(vessel, position, port)
        red_physical = sum(1 for i in physical_issues if i.level == "error")

        occupancy_issues = validate_position_availability(
            position.id,
            call_date,
            exclude_booking_id,
        )
        occupied = sum(
            1
            for i in occupancy_issues
            if i.code in {"position_occupied", "lta_priority_conflict"}
        )

        recalc_issues = validate_loa_recalc(
            vessel,
            position,
            call_date,
            exclude_booking_id=exclude_booking_id,
            port=port,
        )
        red_recalc = sum(
            1
            for i in recalc_issues
            if i.code == "loa_recalc_sum_red"
            or i.severity == "red"
            or (i.detail or {}).get("overhang_m")
        )

        rank = (
            occupied,
            red_physical,
            red_recalc,
            *_rank_position(vessel, position, port),
        )
        candidates.append((rank, position))

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
    """Return preferred pier if active; conflicts are non-blocking."""
    reserved = reserved_position_ids or set()
    if reserved & related_position_ids(preferred_position_id):
        return None
    try:
        position = (
            Position.objects.select_related("berth")
            .prefetch_related("component_links")
            .get(
                pk=preferred_position_id,
                port_id=port.id,
                is_active=True,
            )
        )
    except Position.DoesNotExist:
        return None
    if position_is_combined(position):
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
