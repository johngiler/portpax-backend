from rest_framework import serializers

from apps.catalogs.models import PortImage


class PortImageSerializer(serializers.ModelSerializer):
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
