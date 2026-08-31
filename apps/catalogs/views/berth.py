from rest_framework import filters, viewsets

from apps.catalogs.models import Berth
from apps.catalogs.serializers import BerthSerializer
from apps.catalogs.services.port_catalog_audit import (
    berth_audit_entity,
    diff_berth_snapshots,
    snapshot_berth,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class BerthViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = Berth.objects.select_related("port")
    serializer_class = BerthSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name"]
    ordering_fields = ["sort_order", "code", "created_at"]
    ordering = ["sort_order", "code"]
    port_access_field = "port_id"
    port_audit_resource = "berth"
    port_audit_label = "el muelle"

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "port"):
            instance = Berth.objects.select_related("port").get(pk=instance.pk)
        return snapshot_berth(instance)

    def get_port_audit_diff(self, before, after):
        return diff_berth_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return berth_audit_entity(snap)

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
