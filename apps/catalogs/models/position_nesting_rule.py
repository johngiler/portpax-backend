from django.db import models

from apps.catalogs.models.port import Port
from apps.catalogs.models.position import Position


class PositionNestingRule(models.Model):
    """
    First-in / last-out nesting between two pier positions (double parking).

    outer = entrance / first-in (e.g. E1)
    inner = fondo / last-out (e.g. E2)

    When both are occupied the same day:
    - ETA(inner) >= ETA(outer) if enforce_eta
    - ETD(inner) <= ETD(outer) if enforce_etd
    """

    port = models.ForeignKey(
        Port,
        on_delete=models.CASCADE,
        related_name="position_nesting_rules",
    )
    outer_position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="nesting_as_outer",
        help_text="Entrance / first-in position (must arrive first).",
    )
    inner_position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="nesting_as_inner",
        help_text="Fondo / last-out position (must not arrive before outer).",
    )
    enforce_eta = models.BooleanField(
        default=True,
        help_text="Require inner ETA >= outer ETA when both occupy the same day.",
    )
    enforce_etd = models.BooleanField(
        default=True,
        help_text="Require inner ETD <= outer ETD when both occupy the same day.",
    )
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port", "outer_position", "inner_position"]
        constraints = [
            models.UniqueConstraint(
                fields=["port", "outer_position", "inner_position"],
                name="uniq_position_nesting_rule",
            ),
            models.CheckConstraint(
                condition=~models.Q(outer_position=models.F("inner_position")),
                name="position_nesting_distinct",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.port.code}: first-in {self.outer_position.code} "
            f"→ fondo {self.inner_position.code}"
        )
