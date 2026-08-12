from datetime import date

from apps.bookings.models import Booking
from apps.bookings.services.validation.rules import (
    find_occupying_booking,
    validate_booking,
)
from apps.catalogs.models import Port, Position, Vessel
from apps.catalogs.utils.position_code import position_short_code


def validate_booking_instance(
    booking: Booking,
    *,
    acknowledge_combined_red: bool = False,
) -> dict:
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
        eta=booking.eta,
        etd=booking.etd,
        exclude_booking_id=booking.id,
        acknowledge_combined_red=acknowledge_combined_red,
    )


def validate_booking_params(
    *,
    port_id: int,
    vessel_id: int,
    call_dates: list[date],
    position_id: int | None = None,
    eta=None,
    etd=None,
    acknowledge_combined_red: bool = False,
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
            eta=eta,
            etd=etd,
            acknowledge_combined_red=acknowledge_combined_red,
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


def suggest_positions(
    port_id: int,
    vessel_id: int,
    call_date: date,
    *,
    exclude_booking_id: int | None = None,
) -> list[dict]:
    """Pier positions that fit LOA/draft; ordered by first-in (sort_order)."""
    from apps.bookings.constants import LTA_SOFT_FAIL_CODES
    from apps.bookings.services.position_assignment import auto_assign_position
    from apps.bookings.services.validation.loa_recalc import effective_max_loa_m

    # Still list these so the UI can offer replace / show occupied slots.
    suggest_allow_codes = LTA_SOFT_FAIL_CODES | {"position_occupied"}

    vessel = Vessel.objects.get(pk=vessel_id)
    port = Port.objects.get(pk=port_id)
    recommended = auto_assign_position(
        port,
        vessel,
        call_date,
        exclude_booking_id=exclude_booking_id,
    )

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
            exclude_booking_id=exclude_booking_id,
        )
        hard_errors = [
            i
            for i in result["errors"]
            if i.get("code") not in suggest_allow_codes
        ]
        soft_notes = [
            i for i in result["errors"] if i.get("code") in suggest_allow_codes
        ]
        if not hard_errors:
            occupant_booking = find_occupying_booking(
                position.id,
                call_date,
                exclude_booking_id,
            )
            occupied = occupant_booking is not None
            occupant = None
            if occupant_booking is not None:
                occupant_position = occupant_booking.position
                occupant_code = (
                    position_short_code(port.code, occupant_position.code)
                    if occupant_position is not None
                    else position_short_code(port.code, position.code)
                )
                occupant = {
                    "booking_id": occupant_booking.id,
                    "booking_code": occupant_booking.booking_code,
                    "status": occupant_booking.status,
                    "vessel_name": (
                        occupant_booking.vessel.name
                        if occupant_booking.vessel_id
                        else ""
                    ),
                    "shipping_line_name": (
                        occupant_booking.shipping_line.name
                        if occupant_booking.shipping_line_id
                        else ""
                    ),
                    "position_code": occupant_code,
                    "call_date": call_date.isoformat(),
                    "eta": (
                        occupant_booking.eta.isoformat()
                        if occupant_booking.eta
                        else None
                    ),
                    "etd": (
                        occupant_booking.etd.isoformat()
                        if occupant_booking.etd
                        else None
                    ),
                }
            remaining_max = effective_max_loa_m(
                position,
                call_date,
                exclude_booking_id=exclude_booking_id,
            )
            suggestions.append(
                {
                    "id": position.id,
                    "code": position_short_code(port.code, position.code),
                    "position_type": position.position_type,
                    "max_loa_m": str(remaining_max) if remaining_max is not None else None,
                    "occupied": occupied,
                    "occupant": occupant,
                    "recommended": recommended is not None and position.id == recommended.id,
                    "warnings": [*result["warnings"], *soft_notes],
                }
            )

    return suggestions
