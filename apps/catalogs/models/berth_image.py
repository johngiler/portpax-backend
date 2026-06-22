from django.db import models


class BerthImage(models.Model):
    """Gallery images for a berth (muelle photos)."""

    berth = models.ForeignKey(
        "catalogs.Berth",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="berths/gallery/")
    caption = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_cover = models.BooleanField(
        default=False,
        help_text="Cover image shown on berth cards.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.caption or f"Image #{self.pk}"
