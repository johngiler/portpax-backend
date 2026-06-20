from rest_framework import serializers

from apps.catalogs.models import Vessel


class VesselSerializer(serializers.ModelSerializer):
    shipping_line_name = serializers.CharField(source="shipping_line.name", read_only=True)
    group_name = serializers.CharField(source="shipping_line.group.name", read_only=True)
    total_persons = serializers.SerializerMethodField()

    class Meta:
        model = Vessel
        fields = [
            "id",
            "shipping_line",
            "shipping_line_name",
            "group_name",
            "name",
            "vessel_class",
            "gross_tonnage",
            "pax_capacity",
            "crew_capacity",
            "total_persons",
            "loa_m",
            "beam_m",
            "draft_m",
            "flag",
            "year_built",
            "segment",
            "size_category",
            "mooring_line_count",
            "bollard_count",
            "bollard_swl_t",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "total_persons", "created_at", "updated_at"]

    def get_total_persons(self, obj: Vessel) -> int | None:
        return obj.total_persons
