from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Event(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DELETED = "deleted", "Deleted"
        CONFLICT_DETECTED = "conflict_detected", "Conflict detected"
        CONFLICT_RESOLVED = "conflict_resolved", "Conflict resolved"
        CONFLICT_UPDATED = "conflict_updated", "Conflict updated"

    class Artifact(models.TextChoices):
        WIZARD = "wizard", "Wizard"
        MASS_IMPORT = "mass_import", "Mass import"
        MASS_UPDATE = "mass_update", "Mass update"
        LTA_GENERATE = "lta_generate", "LTA generate"
        LTA_AGREEMENT = "lta_agreement", "LTA agreement"
        BERTHING_IMPORT = "berthing_import", "Berthing import"
        CONFLICT = "conflict", "Conflict"

    class Target(models.TextChoices):
        BOOKING_DETAIL = "booking_detail", "Booking detail"
        BOOKINGS_HISTORY = "bookings_history", "Bookings history"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    event = models.CharField(max_length=32, choices=Event.choices)
    artifact = models.CharField(
        max_length=32,
        choices=Artifact.choices,
        blank=True,
        default="",
    )
    target = models.CharField(max_length=32, choices=Target.choices)
    message = models.CharField(max_length=512)
    actor_display = models.CharField(max_length=150, blank=True, default="")
    booking_id = models.PositiveIntegerField(null=True, blank=True)
    booking_code = models.CharField(max_length=64, blank=True, default="")
    port_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    batch_id = models.PositiveIntegerField(null=True, blank=True)
    affected_count = models.PositiveIntegerField(default=1)
    history_type_filter = models.CharField(max_length=64, blank=True, default="")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "read_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.recipient_id} · {self.event} · {self.message[:40]}"
