from rest_framework import serializers

from apps.catalogs.models import ShippingLine
from apps.core.serializers.mixins import WebPImageFieldsMixin


class ShippingLineSerializer(WebPImageFieldsMixin, serializers.ModelSerializer):
    webp_image_fields = ("logo",)
    group_name = serializers.CharField(source="group.name", read_only=True)
    vessel_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ShippingLine
        fields = [
            "id",
            "group",
            "group_name",
            "code",
            "name",
            "logo",
            "is_active",
            "vessel_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "vessel_count", "created_at", "updated_at"]

    def validate_code(self, value: str) -> str:
        return value.strip().lower().replace(" ", "_")
