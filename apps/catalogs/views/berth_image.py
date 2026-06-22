from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import BerthImage
from apps.catalogs.serializers import BerthImageSerializer


class BerthImageViewSet(viewsets.ModelViewSet):
    queryset = BerthImage.objects.select_related("berth")
    serializer_class = BerthImageSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["sort_order", "id"]
    ordering = ["sort_order", "id"]

    def get_queryset(self):
        qs = super().get_queryset()
        berth_id = self.request.query_params.get("berth")
        if berth_id:
            qs = qs.filter(berth_id=berth_id)
        return qs
