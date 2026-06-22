from django.db import models

from apps.catalogs.models.berth import Berth
from apps.catalogs.models.port import Port


class PositionType(models.TextChoices):
    PIER = "pier", "Pier"
    ANCHORAGE = "anchorage", "Anchorage"


class Position(models.Model):
    """Operational berth slot for booking (P1, P2, A1, M1, …)."""

    port = models.ForeignKey(Port, on_delete=models.CASCADE, related_name="positions")
    berth = models.ForeignKey(
        Berth,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="positions",
        help_text="Null for anchorage-only positions.",
    )
    code = models.CharField(max_length=32)
    position_type = models.CharField(max_length=16, choices=PositionType.choices)
    max_loa_m = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Max LOA (eslora) for this slot (m).",
    )
    min_draft_m = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Min depth / calado at berth line (m).",
    )
    bollard_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Number of bollards (bitas) at this position.",
    )
    fender_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Number of fenders (defensas) at this position.",
    )
    out_of_service = models.BooleanField(default=False)
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    is_projection = models.BooleanField(
        default=False,
        help_text="Future-phase capacity; not current operational state (doc §5.4).",
    )
    notes = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port", "sort_order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["port", "code"], name="uniq_position_code_per_port"),
        ]

    def __str__(self) -> str:
        return f"{self.port.code}:{self.code}"
