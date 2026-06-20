from rest_framework import serializers

from apps.catalogs.models import Position


class PositionSerializer(serializers.ModelSerializer):
    berth_code = serializers.CharField(
        source="berth.code",
        read_only=True,
        allow_null=True,
        default="",
    )

    class Meta:
        model = Position
        fields = [
            "id",
            "port",
            "berth",
            "berth_code",
            "code",
            "position_type",
            "max_loa_m",
            "min_draft_m",
            "out_of_service",
            "effective_from",
            "effective_until",
            "is_projection",
            "notes",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "berth_code", "created_at", "updated_at"]
