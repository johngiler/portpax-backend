from rest_framework import serializers

from apps.catalogs.serializers.shipping_line import ShippingLineSerializer
from apps.catalogs.serializers.vessel import VesselSerializer


class ShippingLineDetailSerializer(ShippingLineSerializer):
    vessels = VesselSerializer(many=True, read_only=True)

    class Meta(ShippingLineSerializer.Meta):
        fields = ShippingLineSerializer.Meta.fields + ["vessel_count", "vessels"]
        read_only_fields = ShippingLineSerializer.Meta.read_only_fields + [
            "vessel_count",
            "vessels",
        ]
