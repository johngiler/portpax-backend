from django.db import models

from apps.catalogs.models.position import Position


class PositionComponent(models.Model):
    """Links a combined position to one of its two source pier slots."""

    combined_position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="component_links",
    )
    source_position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        related_name="used_in_combined",
    )
    sort_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["sort_order", "source_position__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["combined_position", "source_position"],
                name="uniq_position_component_source",
            ),
            models.UniqueConstraint(
                fields=["combined_position", "sort_order"],
                name="uniq_position_component_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.combined_position.code} ← {self.source_position.code}"
