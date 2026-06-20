from rest_framework import serializers

from apps.catalogs.models import ShippingLine


class ShippingLineSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = ShippingLine
        fields = [
            "id",
            "group",
            "group_name",
            "code",
            "name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_code(self, value: str) -> str:
        return value.strip().lower().replace(" ", "_")
