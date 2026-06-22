from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import PositionImage
from apps.catalogs.serializers import PositionImageSerializer


class PositionImageViewSet(viewsets.ModelViewSet):
    queryset = PositionImage.objects.select_related("position")
    serializer_class = PositionImageSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "id"]
    ordering = ["sort_order", "id"]

    def get_queryset(self):
        qs = super().get_queryset()
        position_id = self.request.query_params.get("position")
        if position_id:
            qs = qs.filter(position_id=position_id)
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(position__port_id=port_id)
        return qs
