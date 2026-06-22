from django.db.models import Count
from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import Port
from apps.catalogs.serializers import PortSerializer


class PortViewSet(viewsets.ModelViewSet):
    queryset = Port.objects.annotate(position_count=Count("positions")).prefetch_related(
        "positions"
    )
    serializer_class = PortSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name", "commercial_name", "country"]
    ordering_fields = ["name", "code", "country", "created_at"]
    ordering = ["name"]
