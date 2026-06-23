from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import PortFender
from apps.catalogs.serializers import PortFenderSerializer


class PortFenderViewSet(viewsets.ModelViewSet):
    queryset = PortFender.objects.select_related("port")
    serializer_class = PortFenderSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "fender_type"]
    ordering = ["sort_order", "fender_type"]

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
