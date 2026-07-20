from rest_framework import filters, viewsets

from apps.catalogs.models import Berth
from apps.catalogs.serializers import BerthSerializer
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin


class BerthViewSet(UserPortScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Berth.objects.select_related("port")
    serializer_class = BerthSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name"]
    ordering_fields = ["sort_order", "code", "created_at"]
    ordering = ["sort_order", "code"]
    port_access_field = "port_id"

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
