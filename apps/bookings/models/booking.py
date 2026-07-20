from django.conf import settings
from django.db import models

from apps.catalogs.models import Port, Position, ShippingLine, Vessel


class BookingStatus(models.TextChoices):
    NR = "nr", "New Request"
    H = "h", "Hold"
    CO = "co", "Confirmed"
    CL = "cl", "Confirmed LTA"
    LTA = "lta", "LTA"
    LTD = "ltd", "Long Term Deployment"
    R = "r", "Real"
    C = "c", "Cancelled"


class CancellationReason(models.TextChoices):
    BAD_WEATHER = "bad_weather", "Mal tiempo"
    SHIPPING_LINE_DECISION = "shipping_line_decision", "Decisión naviera"
    ITM_DECISION = "itm_decision", "Decisión ITM"


class Booking(models.Model):
    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="bookings")
    shipping_line = models.ForeignKey(
        ShippingLine,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name="bookings")
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )
    call_date = models.DateField()
    eta = models.TimeField(null=True, blank=True, help_text="Estimated time of arrival.")
    etd = models.TimeField(null=True, blank=True, help_text="Estimated time of departure.")
    eta_real = models.TimeField(
        null=True,
        blank=True,
        help_text="Actual time of arrival (set when closing to Real).",
    )
    etd_real = models.TimeField(
        null=True,
        blank=True,
        help_text="Actual time of departure (set when closing to Real).",
    )
    booking_code = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.NR,
    )
    planned_pax = models.PositiveIntegerField(null=True, blank=True)
    actual_pax = models.PositiveIntegerField(null=True, blank=True)
    actual_crew = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    cancellation_reason = models.CharField(
        max_length=40,
        choices=CancellationReason.choices,
        blank=True,
        help_text="Reason selected when cancelling (provisional catalog).",
    )
    cancellation_evidence = models.FileField(
        upload_to="bookings/cancellation_evidence/",
        null=True,
        blank=True,
    )
    confirmation_pdf = models.FileField(
        upload_to="bookings/confirmations/",
        null=True,
        blank=True,
    )
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
