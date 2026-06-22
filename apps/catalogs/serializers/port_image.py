from rest_framework import serializers

from apps.catalogs.models import PortImage
from apps.core.serializers.mixins import WebPImageFieldsMixin


class PortImageSerializer(WebPImageFieldsMixin, serializers.ModelSerializer):
    webp_image_fields = ("image",)
    class Meta:
        model = PortImage
        fields = [
            "id",
            "port",
            "image",
            "caption",
            "sort_order",
            "is_cover",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
