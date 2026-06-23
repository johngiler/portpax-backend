from datetime import date

from apps.catalogs.models import Port, Position, Vessel
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.validation.rules import validate_booking


def validate_booking_instance(booking: Booking) -> dict:
    position = booking.position
    if position is None and booking.position_id:
        position = Position.objects.select_related("berth", "port").filter(
            pk=booking.position_id,
        ).first()
    return validate_booking(
        port=booking.port,
        vessel=booking.vessel,
        call_date=booking.call_date,
        position=position,
        exclude_booking_id=booking.id,
    )


def validate_booking_params(
    *,
    port_id: int,
    vessel_id: int,
    call_dates: list[date],
    position_id: int | None = None,
) -> dict:
    port = Port.objects.get(pk=port_id)
    vessel = Vessel.objects.get(pk=vessel_id)
    position = None
    if position_id:
        position = Position.objects.select_related("berth", "port").get(pk=position_id)

    from apps.bookings.services.position_assignment import no_position_available_warning

    all_errors: list[dict] = []
    all_warnings: list[dict] = []
    by_date: dict[str, dict] = {}

    for call_date in call_dates:
        result = validate_booking(
            port=port,
            vessel=vessel,
            call_date=call_date,
            position=position,
        )
        if position is None:
            missing = no_position_available_warning(port, vessel, call_date)
            if missing:
                result["warnings"].append(missing.as_dict())

        all_errors.extend(result["errors"])
        all_warnings.extend(result["warnings"])
        by_date[call_date.isoformat()] = {
            "errors": result["errors"],
            "warnings": result["warnings"],
            "valid": result["valid"],
        }

    return {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": all_warnings,
        "by_date": by_date,
    }


def suggest_positions(port_id: int, vessel_id: int, call_date: date) -> list[dict]:
    """Pier positions that fit LOA/draft; ordered by first-in (sort_order)."""
    from apps.bookings.services.position_assignment import auto_assign_position

    vessel = Vessel.objects.get(pk=vessel_id)
    port = Port.objects.get(pk=port_id)
    recommended = auto_assign_position(port, vessel, call_date)

    positions = Position.objects.filter(
        port_id=port_id,
        is_active=True,
    ).select_related("berth").order_by("sort_order", "code")

    suggestions: list[dict] = []
    for position in positions:
        result = validate_booking(
            port=port,
            vessel=vessel,
            call_date=call_date,
            position=position,
        )
        if not any(i["level"] == "error" for i in result["errors"]):
            occupied = Booking.objects.filter(
                position=position,
                call_date=call_date,
                status__in=[BookingStatus.REQUESTED, BookingStatus.CONFIRMED],
            ).exists()
            suggestions.append(
                {
                    "id": position.id,
                    "code": position.code,
                    "position_type": position.position_type,
                    "max_loa_m": str(position.max_loa_m) if position.max_loa_m else None,
                    "occupied": occupied,
                    "recommended": recommended is not None and position.id == recommended.id,
                    "warnings": result["warnings"],
                }
            )

    return suggestions
