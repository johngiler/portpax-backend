from rest_framework import serializers

from apps.catalogs.models import Berth


class BerthSerializer(serializers.ModelSerializer):
    class Meta:
        model = Berth
        fields = [
            "id",
            "port",
            "code",
            "name",
            "length_m",
            "width_m",
            "walkway_length_m",
            "walkway_width_m",
            "min_draft_m",
            "notes",
            "latitude",
            "longitude",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
