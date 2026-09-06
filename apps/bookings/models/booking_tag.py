from django.conf import settings
from django.db import models


class BookingTag(models.Model):
    """Reusable operator label for filtering sets of bookings (reports, history)."""

    name = models.CharField(max_length=120, unique=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_tags_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "booking tag"
        verbose_name_plural = "booking tags"

    def __str__(self) -> str:
        return self.name
