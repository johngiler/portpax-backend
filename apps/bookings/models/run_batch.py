from django.conf import settings
from django.db import models

from apps.audit.services.deletion import ImmutableAuditModel


class BookingRunBatch(ImmutableAuditModel):
    """
    Grouped booking activity for one process run.

    Used for mass update, LTA generate, and LTA link/unlink/resync so the
    history feed shows one card instead of N audit rows.
    """

    class Kind(models.TextChoices):
        MASS_UPDATE = "mass_update", "Actualización masiva"
        LTA_GENERATE = "lta_generate", "Creación LTA"
        LTA_AGREEMENT = "lta_agreement", "Actualización acuerdos LTA"

    kind = models.CharField(max_length=32, choices=Kind.choices, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_run_batches",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    label = models.CharField(max_length=255)
    tag = models.ForeignKey(
        "bookings.BookingTag",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="run_batches",
        help_text="Only used for mass_update runs.",
    )
    booking_ids = models.JSONField(default=list, blank=True)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    # Union of field keys changed across mass_update rows (e.g. position_id, status).
    changed_fields = models.JSONField(default=list, blank=True)
    failures = models.JSONField(default=list, blank=True)
    meta = models.JSONField(
        default=dict,
        blank=True,
        help_text="Process context (agreement_code, job_kind, …).",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "booking run batch"
        verbose_name_plural = "booking run batches"

    def __str__(self) -> str:
        return f"{self.label} · {self.success_count}"
