from rest_framework import serializers

from apps.catalogs.models import Position


class PositionSerializer(serializers.ModelSerializer):
    berth_code = serializers.CharField(
        source="berth.code",
        read_only=True,
        allow_null=True,
        default="",
    )
    port_name = serializers.CharField(source="port.name", read_only=True)
    port_code = serializers.CharField(source="port.code", read_only=True)

    class Meta:
        model = Position
        fields = [
            "id",
            "port",
            "port_name",
            "port_code",
            "berth",
            "berth_code",
            "code",
            "position_type",
            "max_loa_m",
            "min_draft_m",
            "bollard_count",
            "fender_count",
            "out_of_service",
            "effective_from",
            "effective_until",
            "is_projection",
            "notes",
            "latitude",
            "longitude",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "berth_code", "port_name", "port_code", "created_at", "updated_at"]
