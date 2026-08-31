from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import PortBollard
from apps.catalogs.serializers import PortBollardSerializer
from apps.catalogs.services.port_catalog_audit import (
    bollard_audit_entity,
    diff_bollard_snapshots,
    snapshot_bollard,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class PortBollardViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = PortBollard.objects.select_related("port")
    serializer_class = PortBollardSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "capacity_t"]
    ordering = ["sort_order", "-capacity_t"]
    port_access_field = "port_id"
    port_audit_resource = "bollard"
    port_audit_label = "la bita"

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "port"):
            instance = PortBollard.objects.select_related("port").get(pk=instance.pk)
        return snapshot_bollard(instance)

    def get_port_audit_diff(self, before, after):
        return diff_bollard_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return bollard_audit_entity(snap)

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
