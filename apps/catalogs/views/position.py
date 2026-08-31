from django.db.models import Prefetch
from rest_framework import filters, viewsets

from apps.catalogs.models import Position, PositionComponent
from apps.catalogs.serializers import PositionSerializer
from apps.catalogs.services.port_catalog_audit import (
    diff_position_snapshots,
    position_audit_entity,
    snapshot_position,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class PositionViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = Position.objects.select_related("port", "berth").prefetch_related(
        "bollard_lines__port_bollard",
        "fender_lines__port_fender",
    )
    serializer_class = PositionSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "berth__code"]
    ordering_fields = ["sort_order", "code", "created_at"]
    ordering = ["sort_order", "code"]
    port_access_field = "port_id"
    port_audit_resource = "position"
    port_audit_label = "la posición"

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "_prefetched_objects_cache"):
            instance = (
                Position.objects.select_related("port", "berth")
                .prefetch_related(
                    "bollard_lines__port_bollard",
                    "fender_lines__port_fender",
                )
                .get(pk=instance.pk)
            )
        return snapshot_position(instance)

    def get_port_audit_diff(self, before, after):
        return diff_position_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return position_audit_entity(snap)

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)

        combinable = self.request.query_params.get("combinable")
        if combinable in ("1", "true", "True"):
            combined_ids = PositionComponent.objects.values_list("combined_position_id", flat=True)
            qs = qs.filter(position_type="pier").exclude(id__in=combined_ids)

        qs = qs.prefetch_related(
            Prefetch(
                "component_links",
                queryset=PositionComponent.objects.select_related("source_position").order_by(
                    "sort_order", "source_position__code"
                ),
                to_attr="_prefetched_component_links",
            )
        )
        return qs.distinct()
