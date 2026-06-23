from rest_framework import serializers

from apps.catalogs.models import Port
from apps.catalogs.utils.position_code import position_short_code
from apps.core.serializers.mixins import WebPImageFieldsMixin


class PortSerializer(WebPImageFieldsMixin, serializers.ModelSerializer):
    webp_image_fields = ("logo",)
    position_count = serializers.IntegerField(read_only=True, default=0)
    position_codes = serializers.SerializerMethodField()

    class Meta:
        model = Port
        fields = [
            "id",
            "code",
            "name",
            "commercial_name",
            "country",
            "region",
            "latitude",
            "longitude",
            "status",
            "min_berth_draft_m",
            "anchorage_slot_count",
            "fender_count",
            "largest_vessel_recorded",
            "largest_vessel_loa_m",
            "notes",
            "logo",
            "is_active",
            "position_count",
            "position_codes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "largest_vessel_recorded",
            "largest_vessel_loa_m",
            "position_count",
            "position_codes",
            "created_at",
            "updated_at",
        ]

    def get_position_codes(self, obj: Port) -> list[str]:
        positions = obj.positions.all()
        if hasattr(positions, "order_by"):
            positions = positions.order_by("sort_order", "code")
        return [position_short_code(obj.code, p.code) for p in positions]

    def validate_code(self, value: str) -> str:
        return value.strip().lower().replace(" ", "_")
