from django.conf import settings
from django.db import models

from apps.catalogs.models import Port, ShippingLine, Vessel


class BookingStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"


class Booking(models.Model):
    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="bookings")
    shipping_line = models.ForeignKey(
        ShippingLine,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name="bookings")
    call_date = models.DateField()
    booking_code = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.REQUESTED,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-call_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["port", "vessel", "call_date"],
                name="bookings_unique_port_vessel_call_date",
            ),
        ]

    def __str__(self) -> str:
        return self.booking_code
