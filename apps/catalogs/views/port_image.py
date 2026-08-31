from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import PortImage
from apps.catalogs.serializers import PortImageSerializer
from apps.catalogs.services.port_catalog_audit import (
    diff_port_image_snapshots,
    port_image_audit_entity,
    snapshot_port_image,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class PortImageViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = PortImage.objects.select_related("port")
    serializer_class = PortImageSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "id"]
    ordering = ["sort_order", "id"]
    port_access_field = "port_id"
    port_audit_resource = "port_image"
    port_audit_label = "la imagen del puerto"

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "port"):
            instance = PortImage.objects.select_related("port").get(pk=instance.pk)
        return snapshot_port_image(instance)

    def get_port_audit_diff(self, before, after):
        return diff_port_image_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return port_image_audit_entity(snap)

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
