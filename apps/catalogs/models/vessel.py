from django.db import models

from apps.catalogs.models.shipping_line import ShippingLine


class Vessel(models.Model):
    """Cruise ship — source: docs/Base_Datos_Cruceros.xlsx."""

    shipping_line = models.ForeignKey(
        ShippingLine,
        on_delete=models.PROTECT,
        related_name="vessels",
    )
    name = models.CharField(max_length=128)
    logo = models.ImageField(
        upload_to="vessels/logos/",
        blank=True,
        null=True,
        help_text="Vessel image thumbnail (single image).",
    )
    vessel_class = models.CharField(max_length=128, blank=True)
    gross_tonnage = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pax_capacity = models.PositiveIntegerField(null=True, blank=True)
    crew_capacity = models.PositiveIntegerField(null=True, blank=True)
    loa_m = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    beam_m = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    draft_m = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    flag = models.CharField(max_length=64, blank=True)
    year_built = models.PositiveSmallIntegerField(null=True, blank=True)
    segment = models.CharField(max_length=64, blank=True)
    size_category = models.CharField(max_length=64, blank=True)
    mooring_line_count = models.PositiveSmallIntegerField(null=True, blank=True)
    bollard_count = models.PositiveSmallIntegerField(null=True, blank=True)
    bollard_swl_t = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["shipping_line", "name"],
                name="catalogs_vessel_line_name_uniq",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def total_persons(self) -> int | None:
        if self.pax_capacity is None and self.crew_capacity is None:
            return None
        return (self.pax_capacity or 0) + (self.crew_capacity or 0)
