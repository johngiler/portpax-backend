from django.db import models

from apps.catalogs.models.port_fender import PortFender
from apps.catalogs.models.position import Position


class PositionFenderLine(models.Model):
    """Fenders assigned to a position from port inventory (partial quantities allowed)."""

    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="fender_lines",
    )
    port_fender = models.ForeignKey(
        PortFender,
        on_delete=models.PROTECT,
        related_name="position_lines",
    )
    quantity = models.PositiveSmallIntegerField()
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["position", "port_fender"],
                name="uniq_position_fender_line",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity}× {self.port_fender}"
