from django.conf import settings
from django.db import models

from apps.audit.services.deletion import ImmutableAuditModel


class BookingAuditEntry(ImmutableAuditModel):
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    booking_code = models.CharField(max_length=64, blank=True, default="")
    port_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Port snapshot for ACL filters after booking deletion.",
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
        ref = self.booking_code or self.booking_id or "?"
        return f"{ref} · {self.action}"
