from apps.bookings.models import Booking, BookingStatus


class BookingStatusError(Exception):
    pass


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.REQUESTED: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.CANCELLED},
    BookingStatus.CANCELLED: set(),
}


def update_booking_status(booking: Booking, new_status: str) -> Booking:
    allowed = ALLOWED_TRANSITIONS.get(booking.status, set())
    if new_status not in allowed:
        current = booking.get_status_display()
        target = dict(BookingStatus.choices).get(new_status, new_status)
        raise BookingStatusError(f"No se puede cambiar de «{current}» a «{target}».")

    booking.status = new_status
    booking.save(update_fields=["status", "updated_at"])
    return booking
