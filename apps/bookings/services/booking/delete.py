from apps.bookings.models import Booking, BookingStatus


class BookingDeleteError(Exception):
    pass


def delete_cancelled_booking(booking: Booking) -> None:
    if booking.status != BookingStatus.C:
        raise BookingDeleteError("Solo se pueden eliminar reservas canceladas.")
    booking.delete()
