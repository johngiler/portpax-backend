from django.db.models import Count, Prefetch
from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import Berth, Port, Position
from apps.catalogs.serializers import PortDetailSerializer, PortSerializer


class PortViewSet(viewsets.ModelViewSet):
    serializer_class = PortSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name", "commercial_name", "country"]
    ordering_fields = ["name", "code", "country", "created_at"]
    ordering = ["name"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PortDetailSerializer
        return PortSerializer

    def get_queryset(self):
        base = Port.objects.annotate(position_count=Count("positions"))
        if self.action == "retrieve":
            positions_qs = Position.objects.prefetch_related(
                "images",
                "port_bollards",
                "port_fenders",
            ).order_by(
                "sort_order", "code"
            )
            berths_qs = Berth.objects.prefetch_related("images").order_by("sort_order", "code")
            return base.prefetch_related(
                Prefetch("berths", queryset=berths_qs),
                Prefetch("positions", queryset=positions_qs),
                "bollards",
                "fenders",
                "images",
            )
        return base.prefetch_related("positions")
