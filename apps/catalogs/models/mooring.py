from django.db import models

from apps.catalogs.models.port import Port
from apps.catalogs.models.position import Position


class MooringScenario(models.Model):
    """Multi-vessel mooring layout from pier PDFs (doc §3 per-port configurations)."""

    port = models.ForeignKey(Port, on_delete=models.CASCADE, related_name="mooring_scenarios")
    name = models.CharField(max_length=128)
    vessel_count = models.PositiveSmallIntegerField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    is_projection = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port", "name"]

    def __str__(self) -> str:
        return f"{self.port.code} — {self.name}"


class MooringScenarioSlot(models.Model):
    """One vessel slot within a mooring scenario (E1, N1, P1, … + max LOA)."""

    scenario = models.ForeignKey(
        MooringScenario,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mooring_slots",
    )
    slot_label = models.CharField(max_length=32, blank=True)
    max_loa_m = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["scenario", "sort_order", "slot_label"]

    def __str__(self) -> str:
        label = self.slot_label or (self.position.code if self.position_id else "?")
        return f"{self.scenario} / {label}"
