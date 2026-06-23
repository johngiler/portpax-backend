from rest_framework import serializers

from apps.catalogs.models import Port
from apps.catalogs.serializers.berth import BerthSerializer
from apps.catalogs.serializers.port import PortSerializer
from apps.catalogs.serializers.port_bollard import PortBollardSerializer
from apps.catalogs.serializers.port_fender import PortFenderSerializer
from apps.catalogs.serializers.port_image import PortImageSerializer
from apps.catalogs.serializers.berth_image import BerthImageSerializer
from apps.catalogs.serializers.position import PositionSerializer
from apps.catalogs.serializers.position_image import PositionImageSerializer


def _cover_image_url(obj, images_attr: str, serializer_context) -> str | None:
    images = getattr(obj, images_attr).all()
    cover = next((img for img in images if img.is_cover), None)
    chosen = cover or (images[0] if images else None)
    if not chosen or not chosen.image:
        return None
    request = serializer_context.get("request")
    url = chosen.image.url
    if request:
        return request.build_absolute_uri(url)
    return url


class BerthDetailSerializer(BerthSerializer):
    images = BerthImageSerializer(many=True, read_only=True)
    cover_image = serializers.SerializerMethodField()

    class Meta(BerthSerializer.Meta):
        fields = BerthSerializer.Meta.fields + ["images", "cover_image"]
        read_only_fields = BerthSerializer.Meta.read_only_fields + ["images", "cover_image"]

    def get_cover_image(self, obj) -> str | None:
        return _cover_image_url(obj, "images", self.context)


class PositionDetailSerializer(PositionSerializer):
    images = PositionImageSerializer(many=True, read_only=True)
    cover_image = serializers.SerializerMethodField()

    class Meta(PositionSerializer.Meta):
        fields = PositionSerializer.Meta.fields + ["images", "cover_image"]
        read_only_fields = PositionSerializer.Meta.read_only_fields + ["images", "cover_image"]

    def get_cover_image(self, obj) -> str | None:
        return _cover_image_url(obj, "images", self.context)


class PortDetailSerializer(PortSerializer):
    berths = BerthDetailSerializer(many=True, read_only=True)
    positions = PositionDetailSerializer(many=True, read_only=True)
    bollards = PortBollardSerializer(many=True, read_only=True)
    fenders = PortFenderSerializer(many=True, read_only=True)
    images = PortImageSerializer(many=True, read_only=True)
    bollard_total = serializers.SerializerMethodField()
    fender_total = serializers.SerializerMethodField()

    class Meta(PortSerializer.Meta):
        fields = PortSerializer.Meta.fields + [
            "berths",
            "positions",
            "bollards",
            "fenders",
            "bollard_total",
            "fender_total",
            "images",
        ]
        read_only_fields = PortSerializer.Meta.read_only_fields + [
            "berths",
            "positions",
            "bollards",
            "fenders",
            "bollard_total",
            "fender_total",
            "images",
        ]

    def get_bollard_total(self, obj: Port) -> int:
        return sum(b.quantity for b in obj.bollards.all() if b.is_active)

    def get_fender_total(self, obj: Port) -> int:
        return sum(f.quantity for f in obj.fenders.all() if f.is_active)
