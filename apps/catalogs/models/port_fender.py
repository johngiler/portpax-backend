from django.db import models


class PortFender(models.Model):
    """Port-level fender inventory by type (docs §4)."""

    port = models.ForeignKey(
        "catalogs.Port",
        on_delete=models.CASCADE,
        related_name="fenders",
    )
    fender_type = models.CharField(max_length=64)
    quantity = models.PositiveSmallIntegerField(default=1)
    sort_order = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "fender_type"]

    def __str__(self) -> str:
        return f"{self.quantity}× {self.fender_type}"
