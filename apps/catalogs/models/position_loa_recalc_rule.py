from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.catalogs.models.port import Port
from apps.catalogs.models.position import Position


class PositionLoaRecalcRule(models.Model):
    """
    Shared pier LOA between two physical positions (e.g. E1 ↔ E2).

    remaining_sibling = max_loa_m − occupant.loa − separation_m

    Traffic light on occupied pier length (both ships + separation):
    - green: sum < yellow_from_m
    - yellow: yellow_from_m ≤ sum < red_from_m
    - red: sum ≥ red_from_m

    where sum = loa_a + loa_b + separation_m (same gap used in remaining_sibling).
    """

    port = models.ForeignKey(
        Port,
        on_delete=models.CASCADE,
        related_name="position_loa_recalc_rules",
    )
    position_a = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="loa_recalc_rules_as_a",
        help_text="First pier in the shared pair (e.g. E1).",
    )
    position_b = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="loa_recalc_rules_as_b",
        help_text="Second pier in the shared pair (e.g. E2).",
    )
    max_loa_m = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        help_text="Total pier max LOA shared by both positions (m).",
    )
    separation_m = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("15.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Gap reserved between the two ships (m).",
    )
    yellow_from_m = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        help_text="Both LOAs + separation at or above this is yellow (m).",
    )
    red_from_m = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        help_text="Both LOAs + separation at or above this is red (m).",
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port", "position_a", "position_b"]
        constraints = [
            models.UniqueConstraint(
                fields=["port", "position_a", "position_b"],
                name="uniq_position_loa_recalc_rule",
            ),
            models.CheckConstraint(
                condition=~models.Q(position_a=models.F("position_b")),
                name="loa_recalc_positions_distinct",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.port.code}: recalc LOA {self.position_a.code}↔{self.position_b.code} "
            f"max {self.max_loa_m} m sep {self.separation_m} m"
        )
