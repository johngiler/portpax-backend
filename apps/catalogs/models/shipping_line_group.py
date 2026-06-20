from django.db import models


class ShippingLineGroup(models.Model):
    """Corporate cruise operator — Excel column Naviera (e.g. Carnival Corporation)."""

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
