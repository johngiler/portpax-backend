from rest_framework import filters, viewsets

from apps.catalogs.models import Vessel
from apps.catalogs.serializers import VesselSerializer


class VesselViewSet(viewsets.ModelViewSet):
    queryset = Vessel.objects.select_related("shipping_line__group")
    serializer_class = VesselSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "vessel_class", "shipping_line__name", "shipping_line__group__name"]
    ordering_fields = ["name", "loa_m", "draft_m", "created_at"]
    ordering = ["name"]
