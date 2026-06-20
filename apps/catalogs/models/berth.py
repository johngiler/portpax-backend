from django.db import models

from apps.catalogs.models.port import Port


class Berth(models.Model):
    """Physical pier / muelle segment at a port."""

    port = models.ForeignKey(Port, on_delete=models.CASCADE, related_name="berths")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=128, blank=True)
    length_m = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    width_m = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    walkway_length_m = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    walkway_width_m = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    min_draft_m = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overrides port min_berth_draft_m when set.",
    )
    notes = models.TextField(blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port", "sort_order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["port", "code"], name="uniq_berth_code_per_port"),
        ]

    def __str__(self) -> str:
        return f"{self.port.code}:{self.code}"
