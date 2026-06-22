from django.db import models

from apps.catalogs.models.shipping_line_group import ShippingLineGroup


class ShippingLine(models.Model):
    """Operating cruise brand — Excel column Brand (e.g. AIDA Cruises under Carnival Corporation)."""

    group = models.ForeignKey(
        ShippingLineGroup,
        on_delete=models.PROTECT,
        related_name="shipping_lines",
    )
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    logo = models.ImageField(
        upload_to="shipping_lines/logos/",
        blank=True,
        null=True,
        help_text="Shipping line logo thumbnail (single image).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "name"],
                name="catalogs_shippingline_group_name_uniq",
            ),
        ]

    def __str__(self) -> str:
        return self.name
