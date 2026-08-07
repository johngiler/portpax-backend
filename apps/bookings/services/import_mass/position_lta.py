"""Position suggestion + claimable LTA space for mass import preview."""

from __future__ import annotations

from datetime import date
from typing import Any

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services.validation import suggest_positions
from apps.catalogs.utils.position_code import position_short_code
from apps.catalogs.utils.vessel import vessel_is_provisional


def serialize_lta_space_candidate(booking: Booking) -> dict[str, Any]:
    position = booking.position
    port = booking.port
    code = None
    if position is not None and port is not None:
        code = position_short_code(port.code, position.code)
    vessel = booking.vessel if booking.vessel_id else None
    return {
        "id": booking.id,
        "booking_code": booking.booking_code,
        "status": booking.status,
        "vessel_name": vessel.name if vessel is not None else "",
        "vessel_is_provisional": vessel_is_provisional(vessel),
        "shipping_line_name": (
            booking.shipping_line.name if booking.shipping_line_id else ""
        ),
        "position_id": position.id if position else None,
        "position_code": code,
    }


def find_claimable_lta_booking(
    *,
    port_id: int,
    call_date: date,
    shipping_line_id: int,
) -> Booking | None:
    """
    LTA-only placeholder for the same shipping line / port / date.
    Vessel name does not matter — the slot is reserved capacity for that line.
    """
    return (
        Booking.objects.filter(
            port_id=port_id,
            call_date=call_date,
            shipping_line_id=shipping_line_id,
            status=BookingStatus.LTA,
        )
        .select_related("vessel", "position", "port", "shipping_line")
        .order_by("id")
        .first()
    )


def count_claimable_lta_bookings(
    *,
    port_id: int,
    call_date: date,
    shipping_line_id: int,
) -> int:
    return Booking.objects.filter(
        port_id=port_id,
        call_date=call_date,
        shipping_line_id=shipping_line_id,
        status=BookingStatus.LTA,
    ).count()


def pick_suggested_position(
    suggestions: list[dict[str, Any]],
    *,
    preferred_id: int | None,
    claimable_position_id: int | None = None,
    lock_claimable: bool = False,
) -> dict[str, Any] | None:
    # Claiming LTA space: the reserved pier is the slot being claimed.
    if lock_claimable and claimable_position_id is not None:
        for item in suggestions:
            if item.get("id") == claimable_position_id:
                return item
    if preferred_id is not None:
        for item in suggestions:
            if item.get("id") == preferred_id:
                return item
    # No user pick yet: hint the LTA pier if present.
    if claimable_position_id is not None:
        for item in suggestions:
            if item.get("id") == claimable_position_id:
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
    shipping_line_id: int,
    call_date: date,
    preferred_position_id: int | None,
    claim_lta_space: bool,
) -> dict[str, Any]:
    """
    Suggest a pier position and detect a claimable LTA slot for this line.
    When claim_lta_space is set, lock position to the LTA pier.
    """
    candidate = find_claimable_lta_booking(
        port_id=port_id,
        call_date=call_date,
        shipping_line_id=shipping_line_id,
    )
    candidate_payload = (
        serialize_lta_space_candidate(candidate) if candidate else None
    )
    claimable_position_id = (
        candidate.position_id if candidate is not None else None
    )
    locking = bool(claim_lta_space and claimable_position_id)

    suggestions = suggest_positions(port_id, vessel_id, call_date)
    picked = pick_suggested_position(
        suggestions,
        preferred_id=preferred_position_id,
        claimable_position_id=claimable_position_id,
        lock_claimable=locking,
    )
    position_id = int(picked["id"]) if picked else None
    position_code = str(picked["code"]) if picked else None

    if locking and candidate is not None and candidate.position_id:
        position_id = candidate.position_id
        position_code = (
            candidate_payload["position_code"] if candidate_payload else position_code
        )

    extra_lta_count = count_claimable_lta_bookings(
        port_id=port_id,
        call_date=call_date,
        shipping_line_id=shipping_line_id,
    )

    return {
        "position_id": position_id,
        "position_code": position_code,
        "claim_lta_space": bool(claim_lta_space and candidate_payload is not None),
        "lta_space_candidate": candidate_payload,
        "lta_space_count": extra_lta_count,
        "position_locked_to_lta": locking,
    }
