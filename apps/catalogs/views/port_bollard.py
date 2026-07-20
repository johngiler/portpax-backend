from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import PortBollard
from apps.catalogs.serializers import PortBollardSerializer
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin


class PortBollardViewSet(UserPortScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = PortBollard.objects.select_related("port")
    serializer_class = PortBollardSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "capacity_t"]
    ordering = ["sort_order", "-capacity_t"]
    port_access_field = "port_id"

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
