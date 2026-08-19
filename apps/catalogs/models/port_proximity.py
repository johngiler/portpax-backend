from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.catalogs.models.port import Port


class PortProximity(models.Model):
    """
    Precomputed geo proximity between ports (distance + minimum travel time).

    Direction is kept (from_port → to_port) so validation can use the chronological
    gap between calls.
    """

    from_port = models.ForeignKey(
        Port,
        on_delete=models.CASCADE,
        related_name="proximity_from",
    )
    to_port = models.ForeignKey(
        Port,
        on_delete=models.CASCADE,
        related_name="proximity_to",
    )
    distance_km = models.DecimalField(max_digits=10, decimal_places=2)
    travel_hours_min = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Minimum travel time between ports using the configured default speed.",
    )
    speed_knots_used = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text="Knots used to compute travel time (hardcoded baseline).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["from_port_id", "to_port_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_port", "to_port"],
                name="catalogs_portproximity_from_to_uniq",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_port=models.F("to_port")),
                name="catalogs_portproximity_from_not_equal_to",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.from_port_id} → {self.to_port_id} ({self.travel_hours_min}h)"

