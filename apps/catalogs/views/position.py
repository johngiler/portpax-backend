from django.db.models import Prefetch
from rest_framework import filters, viewsets

from apps.catalogs.models import Position, PositionComponent
from apps.catalogs.serializers import PositionSerializer


class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.select_related("port", "berth").prefetch_related(
        "bollard_lines__port_bollard",
        "fender_lines__port_fender",
    )
    serializer_class = PositionSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "berth__code"]
    ordering_fields = ["sort_order", "code", "created_at"]
    ordering = ["sort_order", "code"]

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
