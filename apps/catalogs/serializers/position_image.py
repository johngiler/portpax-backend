from rest_framework import serializers

from apps.catalogs.models import PositionImage


class PositionImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PositionImage
        fields = [
            "id",
            "position",
            "image",
            "caption",
            "sort_order",
            "is_cover",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
