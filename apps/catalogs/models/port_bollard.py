from django.db import models


class BollardType(models.TextChoices):
    STANDARD = "standard", "Standard"
    T_HEAD = "t_head", "T-head"
    QUICK_RELEASE = "quick_release", "Quick release hook"
    SINGLE_BRITT = "single_bitt", "Single bitt"
    OTHER = "other", "Other"


class PortBollard(models.Model):
    """Port-level bollard inventory by capacity and type (docs §4)."""

    port = models.ForeignKey(
        "catalogs.Port",
        on_delete=models.CASCADE,
        related_name="bollards",
    )
    capacity_t = models.PositiveSmallIntegerField(
        help_text="Bollard capacity in metric tons (50, 75, 100, 150, 200, …).",
    )
    bollard_type = models.CharField(
        max_length=32,
        choices=BollardType.choices,
        default=BollardType.STANDARD,
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    label = models.CharField(
        max_length=64,
        blank=True,
        help_text="Optional label when type alone is not enough (e.g. Melilla variants).",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "-capacity_t", "bollard_type"]

    def __str__(self) -> str:
        base = f"{self.quantity}× {self.capacity_t} t"
        if self.label:
            return f"{base} ({self.label})"
        if self.bollard_type != BollardType.STANDARD:
            return f"{base} [{self.get_bollard_type_display()}]"
        return base
