"""Shipping-line group is the primary identity fence for bookings."""

from __future__ import annotations

from apps.bookings.services.booking.status import BookingValidationError
from apps.catalogs.models import ShippingLine, Vessel

CREATE_GROUP_MISMATCH_MESSAGE = (
    "El barco y la naviera deben pertenecer al mismo grupo de naviera."
)

UPDATE_GROUP_MISMATCH_MESSAGE = (
    "No se puede mover la reserva a una naviera de otro grupo corporativo. "
    "Cancela esta reserva para liberar la posición y la fecha; "
    "luego crea una nueva en el otro grupo."
)

VESSEL_LINE_MISMATCH_MESSAGE = (
    "El barco debe pertenecer a la naviera seleccionada."
)


def group_mismatch_error(*, for_update: bool = False) -> BookingValidationError:
    message = (
        UPDATE_GROUP_MISMATCH_MESSAGE if for_update else CREATE_GROUP_MISMATCH_MESSAGE
    )
    return BookingValidationError(
        message,
        [
            {
                "code": "shipping_line_group_mismatch",
                "message": message,
                "severity": "error",
            }
        ],
    )


def vessel_line_mismatch_error(message: str | None = None) -> BookingValidationError:
    text = message or VESSEL_LINE_MISMATCH_MESSAGE
    return BookingValidationError(
        text,
        [
            {
                "code": "vessel_line_mismatch",
                "message": text,
                "severity": "error",
            }
        ],
    )


def vessel_group_id(vessel: Vessel) -> int | None:
    line = getattr(vessel, "shipping_line", None)
    if line is None:
        return None
    return line.group_id


def same_shipping_line_group(shipping_line: ShippingLine, vessel: Vessel) -> bool:
    line_group = shipping_line.group_id
    ship_group = vessel_group_id(vessel)
    return line_group is not None and ship_group is not None and line_group == ship_group


def rematch_vessel_by_name(
    name: str,
    *,
    shipping_line_id: int | None = None,
    shipping_line_group_id: int | None = None,
) -> Vessel | None:
    """Unique exact-name match inside a line and/or group. None if ambiguous."""
    ship = (name or "").strip()
    if not ship:
        return None
    qs = Vessel.objects.filter(is_active=True, name__iexact=ship).select_related(
        "shipping_line",
        "shipping_line__group",
    )
    if shipping_line_id:
        qs = qs.filter(shipping_line_id=shipping_line_id)
        if shipping_line_group_id:
            qs = qs.filter(shipping_line__group_id=shipping_line_group_id)
    elif shipping_line_group_id:
        qs = qs.filter(
            shipping_line__group_id=shipping_line_group_id,
            shipping_line__is_active=True,
        )
    matches = list(qs[:5])
    if len(matches) == 1:
        return matches[0]
    return None
