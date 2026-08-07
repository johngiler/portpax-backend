"""Position suggestion + replaceable LTA detection for mass import preview."""

from __future__ import annotations

from datetime import date
from typing import Any

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.validation import suggest_positions
from apps.catalogs.utils.position_code import position_short_code


def serialize_lta_candidate(booking: Booking) -> dict[str, Any]:
    position = booking.position
    port = booking.port
    code = None
    if position is not None and port is not None:
        code = position_short_code(port.code, position.code)
    return {
        "id": booking.id,
        "booking_code": booking.booking_code,
        "vessel_name": booking.vessel.name if booking.vessel_id else "",
        "position_id": position.id if position else None,
        "position_code": code,
    }


def find_replaceable_lta_booking(
    *,
    port_id: int,
    call_date: date,
    vessel_id: int,
    position_id: int | None,
) -> Booking | None:
    """
    LTA-only (not CL): same vessel on that day, or another vessel on the
    chosen/suggested pier position.
    """
    base = (
        Booking.objects.filter(
            port_id=port_id,
            call_date=call_date,
            status=BookingStatus.LTA,
        )
        .select_related("vessel", "position", "port", "shipping_line")
        .order_by("id")
    )

    same_vessel = base.filter(vessel_id=vessel_id).first()
    if same_vessel:
        return same_vessel

    if position_id is not None:
        return base.filter(position_id=position_id).exclude(vessel_id=vessel_id).first()

    return None


def pick_suggested_position(
    suggestions: list[dict[str, Any]],
    *,
    preferred_id: int | None,
) -> dict[str, Any] | None:
    if preferred_id is not None:
        for item in suggestions:
            if item.get("id") == preferred_id:
                return item
    recommended = next((p for p in suggestions if p.get("recommended")), None)
    if recommended and not recommended.get("occupied"):
        return recommended
    free = next((p for p in suggestions if not p.get("occupied")), None)
    if free:
        return free
    if recommended:
        return recommended
    return suggestions[0] if suggestions else None


def resolve_position_and_lta(
    *,
    port_id: int,
    vessel_id: int,
    call_date: date,
    preferred_position_id: int | None,
    replace_lta: bool,
) -> dict[str, Any]:
    """
    Suggest a pier position and detect a replaceable LTA booking on that slot.
    """
    suggestions = suggest_positions(port_id, vessel_id, call_date)
    picked = pick_suggested_position(
        suggestions,
        preferred_id=preferred_position_id,
    )
    position_id = int(picked["id"]) if picked else None
    position_code = str(picked["code"]) if picked else None

    candidate = find_replaceable_lta_booking(
        port_id=port_id,
        call_date=call_date,
        vessel_id=vessel_id,
        position_id=position_id,
    )
    candidate_payload = serialize_lta_candidate(candidate) if candidate else None

    # If replacing and candidate has a pier, prefer that pier for the new row.
    if replace_lta and candidate is not None and candidate.position_id:
        position_id = candidate.position_id
        position_code = (
            candidate_payload["position_code"] if candidate_payload else position_code
        )

    return {
        "position_id": position_id,
        "position_code": position_code,
        "replace_lta": bool(replace_lta and candidate_payload is not None),
        "lta_replace_candidate": candidate_payload,
    }
