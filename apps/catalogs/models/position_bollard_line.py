from django.db import models

from apps.catalogs.models.port_bollard import PortBollard
from apps.catalogs.models.position import Position


class PositionBollardLine(models.Model):
    """Bollards assigned to a position from port inventory (partial quantities allowed)."""

    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="bollard_lines",
    )
    port_bollard = models.ForeignKey(
        PortBollard,
        on_delete=models.PROTECT,
        related_name="position_lines",
    )
    quantity = models.PositiveSmallIntegerField()
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["position", "port_bollard"],
                name="uniq_position_bollard_line",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity}× {self.port_bollard}"
