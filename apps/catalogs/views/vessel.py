from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import Vessel
from apps.catalogs.serializers import VesselSerializer


class VesselViewSet(viewsets.ModelViewSet):
    queryset = Vessel.objects.select_related("shipping_line__group")
    serializer_class = VesselSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "vessel_class", "shipping_line__name", "shipping_line__group__name"]
    ordering_fields = ["name", "loa_m", "draft_m", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        qs = super().get_queryset()
        shipping_line_id = self.request.query_params.get("shipping_line")
        if shipping_line_id:
            qs = qs.filter(shipping_line_id=shipping_line_id)
        return qs
