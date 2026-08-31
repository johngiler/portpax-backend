from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import BerthImage
from apps.catalogs.serializers import BerthImageSerializer
from apps.catalogs.services.port_catalog_audit import (
    berth_image_audit_entity,
    diff_berth_image_snapshots,
    snapshot_berth_image,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class BerthImageViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = BerthImage.objects.select_related("berth__port")
    serializer_class = BerthImageSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "id"]
    ordering = ["sort_order", "id"]
    port_access_field = "berth__port_id"
    port_audit_resource = "berth_image"
    port_audit_label = "la imagen del muelle"

    def resolve_audit_port(self, instance):
        return instance.berth.port

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "berth"):
            instance = BerthImage.objects.select_related("berth__port").get(pk=instance.pk)
        return snapshot_berth_image(instance)

    def get_port_audit_diff(self, before, after):
        return diff_berth_image_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return berth_image_audit_entity(snap)

    def get_port_audit_identifier(self, snap):
        berth_code = snap.get("berth_code")
        caption = snap.get("caption") or f"imagen #{snap.get('id')}"
        if berth_code:
            return f"{berth_code} · {caption}"
        return caption

    def get_queryset(self):
        qs = super().get_queryset()
        berth_id = self.request.query_params.get("berth")
        if berth_id:
            qs = qs.filter(berth_id=berth_id)
        return qs
