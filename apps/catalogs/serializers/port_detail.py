from rest_framework import serializers

from apps.catalogs.models import Port
from apps.catalogs.serializers.berth import BerthSerializer
from apps.catalogs.serializers.port import PortSerializer
from apps.catalogs.serializers.port_bollard import PortBollardSerializer
from apps.catalogs.serializers.port_image import PortImageSerializer
from apps.catalogs.serializers.position import PositionSerializer
from apps.catalogs.serializers.position_image import PositionImageSerializer


class PositionDetailSerializer(PositionSerializer):
    images = PositionImageSerializer(many=True, read_only=True)
    cover_image = serializers.SerializerMethodField()

    class Meta(PositionSerializer.Meta):
        fields = PositionSerializer.Meta.fields + ["images", "cover_image"]
        read_only_fields = PositionSerializer.Meta.read_only_fields + ["images", "cover_image"]

    def get_cover_image(self, obj) -> str | None:
        images = obj.images.all()
        cover = next((img for img in images if img.is_cover), None)
        chosen = cover or (images[0] if images else None)
        if not chosen or not chosen.image:
            return None
        request = self.context.get("request")
        url = chosen.image.url
        if request:
            return request.build_absolute_uri(url)
        return url


class PortDetailSerializer(PortSerializer):
    berths = BerthSerializer(many=True, read_only=True)
    positions = PositionDetailSerializer(many=True, read_only=True)
    bollards = PortBollardSerializer(many=True, read_only=True)
    images = PortImageSerializer(many=True, read_only=True)
    bollard_total = serializers.SerializerMethodField()

    class Meta(PortSerializer.Meta):
        fields = PortSerializer.Meta.fields + [
            "berths",
            "positions",
            "bollards",
            "bollard_total",
            "images",
        ]
        read_only_fields = PortSerializer.Meta.read_only_fields + [
            "berths",
            "positions",
            "bollards",
            "bollard_total",
            "images",
        ]

    def get_bollard_total(self, obj: Port) -> int:
        return sum(b.quantity for b in obj.bollards.all() if b.is_active)
