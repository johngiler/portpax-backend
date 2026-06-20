from rest_framework import filters, viewsets

from apps.catalogs.models import Position
from apps.catalogs.serializers import PositionSerializer


class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.select_related("port", "berth")
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
        return qs
