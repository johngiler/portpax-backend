from django.conf import settings
from django.db import models


class BookingAuditEntry(models.Model):
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=64)
    summary = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_audit_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.booking_id} · {self.action}"
