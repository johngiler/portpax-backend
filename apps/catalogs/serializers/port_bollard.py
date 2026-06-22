from rest_framework import serializers

from apps.catalogs.models import PortBollard


class PortBollardSerializer(serializers.ModelSerializer):
    bollard_type_display = serializers.CharField(
        source="get_bollard_type_display",
        read_only=True,
    )

    class Meta:
        model = PortBollard
        fields = [
            "id",
            "port",
            "capacity_t",
            "bollard_type",
            "bollard_type_display",
            "quantity",
            "label",
            "sort_order",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "bollard_type_display", "created_at", "updated_at"]
