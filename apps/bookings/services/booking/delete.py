from apps.audit.services.record import record_booking_audit
from apps.bookings.models import Booking, BookingStatus


class BookingDeleteError(Exception):
    pass


def delete_cancelled_booking(
    booking: Booking,
    *,
    user=None,
    request=None,
) -> None:
    if booking.status != BookingStatus.C:
        raise BookingDeleteError("Solo se pueden eliminar reservas canceladas.")
    code = booking.booking_code or str(booking.pk)
    record_booking_audit(
        booking,
        action="deleted",
        summary=f"Eliminó la reserva cancelada {code}",
        changes={"deleted": True},
        user=user,
        request=request,
    )
    booking.delete()
