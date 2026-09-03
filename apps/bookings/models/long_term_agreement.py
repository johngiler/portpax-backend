from django.core.exceptions import ValidationError
from django.db import models

from apps.catalogs.models import Port, Position, ShippingLine, Vessel


class LongTermAgreement(models.Model):
    """
    Long-term berthing agreement (LTA).

    Grants early booking windows and strategically reserves weekday/position
    slots for a shipping line. Generar/Regenerar may materialize LTA bookings.
    """

    class BookingPolicy(models.TextChoices):
        STANDARD = "standard", "Standard"
        RCI_STAGGERED = "rci_staggered", "RCI staggered"

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    port = models.ForeignKey(
        Port,
        on_delete=models.PROTECT,
        related_name="long_term_agreements",
    )
    shipping_line = models.ForeignKey(
        ShippingLine,
        on_delete=models.PROTECT,
        related_name="long_term_agreements",
    )
    all_vessels = models.BooleanField(
        default=True,
        help_text="If true, all vessels of the shipping line are covered.",
    )
    vessels = models.ManyToManyField(
        Vessel,
        blank=True,
        related_name="long_term_agreements",
        help_text="Specific vessels when all_vessels is false.",
    )
    positions = models.ManyToManyField(
        Position,
        blank=True,
        related_name="long_term_agreements",
        help_text="Pier positions covered by this agreement (e.g. P1).",
    )
    weekdays = models.JSONField(
        default=list,
        blank=True,
        help_text="ISO weekdays Mon=0 … Sun=6. Empty = every day.",
    )
    interval_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Cadence in days (e.g. 15). Null = no cadence filter.",
    )
    cadence_anchor = models.DateField(
        null=True,
        blank=True,
        help_text="First expected call date for interval_days matching.",
    )
    date_exceptions = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Date-only exceptions to weekday/cadence: "
            "include {kind, date}, skip {kind, date}, "
            "reschedule {kind, from, to}."
        ),
    )
    min_packs = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum packs to fulfill (stored; not enforced in phase 1).",
    )
    advance_months_min = models.PositiveSmallIntegerField(
        default=18,
        help_text="Legacy far-horizon hint (seasonal windows are authoritative).",
    )
    advance_months_max = models.PositiveSmallIntegerField(
        default=32,
        help_text="Legacy max months ahead hint (seasonal windows are authoritative).",
    )
    booking_policy = models.CharField(
        max_length=32,
        choices=BookingPolicy.choices,
        default=BookingPolicy.STANDARD,
        help_text="Standard = any LTA season in depth; RCI = staggered Summer/Winter.",
    )
    lta_depth_blocks = models.PositiveSmallIntegerField(
        default=2,
        help_text="How many 6-month LTA blocks (after open booking) this agreement covers.",
    )
    reserve_foreign_slots = models.BooleanField(
        default=True,
        help_text="When true, blocks other lines on reserved weekday+position in LTA zone.",
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    bookings_generated = models.BooleanField(
        default=False,
        help_text="True after the first successful Generar (or Regenerar) run.",
    )
    notes = models.TextField(blank=True)
    contract_file = models.FileField(
        upload_to="bookings/lta_contracts/",
        null=True,
        blank=True,
        help_text="Optional contract attachment (PDF/DOC).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["port", "shipping_line", "code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.port.code} / {self.shipping_line.code})"

    def clean(self):
        if self.advance_months_min > self.advance_months_max:
            raise ValidationError(
                {"advance_months_min": "Must be less than or equal to advance_months_max."}
            )
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError(
                {"valid_until": "Must be on or after valid_from."}
            )
        if (self.interval_days is None) ^ (self.cadence_anchor is None):
            raise ValidationError(
                {
                    "interval_days": "interval_days and cadence_anchor must be set together.",
                    "cadence_anchor": "interval_days and cadence_anchor must be set together.",
                }
            )
        if self.interval_days is not None and self.interval_days < 1:
            raise ValidationError({"interval_days": "Must be at least 1."})
        weekdays = self.weekdays or []
        if not isinstance(weekdays, list):
            raise ValidationError({"weekdays": "Must be a list of integers 0–6."})
        for day in weekdays:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise ValidationError(
                    {"weekdays": "Each weekday must be an integer 0 (Mon) through 6 (Sun)."}
                )
