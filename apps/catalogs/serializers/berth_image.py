from rest_framework import serializers

from apps.catalogs.models import BerthImage
from apps.core.serializers.mixins import WebPImageFieldsMixin


class BerthImageSerializer(WebPImageFieldsMixin, serializers.ModelSerializer):
    webp_image_fields = ("image",)

    class Meta:
        model = BerthImage
        fields = [
            "id",
            "berth",
            "image",
            "caption",
            "sort_order",
            "is_cover",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
