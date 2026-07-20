from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import PortImage
from apps.catalogs.serializers import PortImageSerializer
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin


class PortImageViewSet(UserPortScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = PortImage.objects.select_related("port")
    serializer_class = PortImageSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "id"]
    ordering = ["sort_order", "id"]
    port_access_field = "port_id"

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
