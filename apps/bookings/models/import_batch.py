from django.conf import settings
from django.db import models
from django.utils import timezone


class BookingImportBatch(models.Model):
    """One mass-import run (Excel file or paste) with created/failed row outcomes."""

    class Source(models.TextChoices):
        FILE = "file", "Archivo"
        PASTE = "paste", "Pegado"

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completada"

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_import_batches",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.FILE,
    )
    label = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    requested_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    created_booking_ids = models.JSONField(default=list, blank=True)
    failures = models.JSONField(default=list, blank=True)
    # Preview-shaped rows not created (failed, skipped, or not selectable) for reprocess.
    retry_rows = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "booking import batch"
        verbose_name_plural = "booking import batches"

    def __str__(self) -> str:
        return f"{self.label} · {self.created_count}/{self.requested_count}"

    def mark_finished(self) -> None:
        self.finished_at = timezone.now()
        self.status = self.Status.COMPLETED
        self.save(
            update_fields=[
                "finished_at",
                "status",
                "created_count",
                "failed_count",
                "created_booking_ids",
                "failures",
                "requested_count",
            ]
        )
