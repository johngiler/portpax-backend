from rest_framework import serializers

from apps.catalogs.models import ShippingLineGroup


class ShippingLineGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingLineGroup
        fields = ["id", "code", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_code(self, value: str) -> str:
        return value.strip().lower().replace(" ", "_")
