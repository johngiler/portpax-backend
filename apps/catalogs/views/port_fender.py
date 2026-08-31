from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import PortFender
from apps.catalogs.serializers import PortFenderSerializer
from apps.catalogs.services.port_catalog_audit import (
    diff_fender_snapshots,
    fender_audit_entity,
    snapshot_fender,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class PortFenderViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = PortFender.objects.select_related("port")
    serializer_class = PortFenderSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "fender_type"]
    ordering = ["sort_order", "fender_type"]
    port_access_field = "port_id"
    port_audit_resource = "fender"
    port_audit_label = "la defensa"

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "port"):
            instance = PortFender.objects.select_related("port").get(pk=instance.pk)
        return snapshot_fender(instance)

    def get_port_audit_diff(self, before, after):
        return diff_fender_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return fender_audit_entity(snap)

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
