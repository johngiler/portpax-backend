from rest_framework import serializers

from apps.catalogs.models import PortFender


class PortFenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortFender
        fields = [
            "id",
            "port",
            "fender_type",
            "quantity",
            "sort_order",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_fender_type(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Requerido.")
        return cleaned

    def validate_quantity(self, value: int) -> int:
        if value < 1:
            raise serializers.ValidationError("Mínimo 1.")
        return value
