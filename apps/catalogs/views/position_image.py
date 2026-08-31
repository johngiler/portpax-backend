from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import PositionImage
from apps.catalogs.serializers import PositionImageSerializer
from apps.catalogs.services.port_catalog_audit import (
    diff_position_image_snapshots,
    position_image_audit_entity,
    snapshot_position_image,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class PositionImageViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = PositionImage.objects.select_related("position__port")
    serializer_class = PositionImageSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "id"]
    ordering = ["sort_order", "id"]
    port_access_field = "position__port_id"
    port_audit_resource = "position_image"
    port_audit_label = "la imagen de la posición"

    def resolve_audit_port(self, instance):
        return instance.position.port

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "position"):
            instance = PositionImage.objects.select_related("position__port").get(pk=instance.pk)
        return snapshot_position_image(instance)

    def get_port_audit_diff(self, before, after):
        return diff_position_image_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return position_image_audit_entity(snap)

    def get_port_audit_identifier(self, snap):
        position_code = snap.get("position_short_code")
        caption = snap.get("caption") or f"imagen #{snap.get('id')}"
        if position_code:
            return f"{position_code} · {caption}"
        return caption

    def get_queryset(self):
        qs = super().get_queryset()
        position_id = self.request.query_params.get("position")
        if position_id:
            qs = qs.filter(position_id=position_id)
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(position__port_id=port_id)
        return qs
