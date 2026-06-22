from django.db import models


class PortOperationalStatus(models.TextChoices):
    OPERATIONAL = "operational", "Operational"
    IN_DEVELOPMENT = "in_development", "In development"
    PLANNED_EXTENSION = "planned_extension", "Planned extension"


class Port(models.Model):
    """ITM cruise port — source: docs/muelles_especificaciones.html."""

    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=128)
    commercial_name = models.CharField(
        max_length=128,
        blank=True,
        help_text="Commercial or terminal name (e.g. Taino Bay for Puerto Plata).",
    )
    country = models.CharField(max_length=64)
    region = models.CharField(max_length=128, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(
        max_length=32,
        choices=PortOperationalStatus.choices,
        default=PortOperationalStatus.OPERATIONAL,
    )
    min_berth_draft_m = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum depth at berth line (m); doc §2 master table.",
    )
    anchorage_slot_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Anchorage positions at port level (e.g. Roatán A1/A2).",
    )
    fender_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Total fenders at port level (docs §2 / §4 inventory).",
    )
    largest_vessel_recorded = models.CharField(max_length=128, blank=True)
    largest_vessel_loa_m = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    logo = models.ImageField(
        upload_to="ports/logos/",
        blank=True,
        null=True,
        help_text="Port logo thumbnail (single image).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        if self.commercial_name:
            return f"{self.name} ({self.commercial_name})"
        return self.name
