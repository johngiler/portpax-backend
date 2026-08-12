from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.catalogs.models.port import Port
from apps.catalogs.models.position import Position


class PositionLoaRecalcRule(models.Model):
    """
    When a non-mega ship occupies one component of a combined slot,
    shrink the sibling's usable LOA:

    remaining = combined.max_loa_m − occupant.loa − min_separation_m
    """

    port = models.ForeignKey(
        Port,
        on_delete=models.CASCADE,
        related_name="position_loa_recalc_rules",
    )
    combined_position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="loa_recalc_rules",
        help_text="Combined slot whose max LOA is shared (e.g. E1+E2).",
    )
    min_separation_m = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("15.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Gap reserved between the two ships (m).",
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port", "combined_position"]
        constraints = [
            models.UniqueConstraint(
                fields=["port", "combined_position"],
                name="uniq_position_loa_recalc_rule",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.port.code}: recalc LOA {self.combined_position.code} "
            f"sep {self.min_separation_m} m"
        )
