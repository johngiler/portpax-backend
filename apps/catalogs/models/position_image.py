from django.db import models


class PositionImage(models.Model):
    """Gallery images for a berth position (muelle / slot photos)."""

    position = models.ForeignKey(
        "catalogs.Position",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="positions/gallery/")
    caption = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_cover = models.BooleanField(
        default=False,
        help_text="Cover image shown on position cards.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.caption or f"Image #{self.pk}"
