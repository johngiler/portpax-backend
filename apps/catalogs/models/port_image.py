from django.db import models


class PortImage(models.Model):
    """Gallery images for a port (renders, photos — distinct from logo thumbnail)."""

    port = models.ForeignKey(
        "catalogs.Port",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="ports/gallery/")
    caption = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_cover = models.BooleanField(
        default=False,
        help_text="Featured image in port gallery (logo remains the grid thumbnail).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.caption or f"Image #{self.pk}"
