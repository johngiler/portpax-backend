from django.db import models

from apps.catalogs.models.port import Port
from apps.catalogs.models.position import Position


class PositionPairConstraint(models.Model):
    """Combined LOA limits when two positions are occupied the same day (RN-05 lite)."""

    port = models.ForeignKey(
        Port,
        on_delete=models.CASCADE,
        related_name="position_pair_constraints",
    )
    position_a = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="pair_constraints_as_a",
    )
    position_b = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="pair_constraints_as_b",
    )
    max_loa_combined = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        help_text="Green threshold: sum of LOAs at or below this is fine (m).",
    )
    max_loa_hard_cap = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        help_text="Red threshold: sum at or above this is a hard-cap warning (m).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port", "position_a", "position_b"]
        constraints = [
            models.UniqueConstraint(
                fields=["port", "position_a", "position_b"],
                name="uniq_position_pair_constraint",
            ),
            models.CheckConstraint(
                condition=~models.Q(position_a=models.F("position_b")),
                name="position_pair_distinct",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.port.code}: {self.position_a.code}+{self.position_b.code} "
            f"≤{self.max_loa_combined}/{self.max_loa_hard_cap} m"
        )
