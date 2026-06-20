from rest_framework import filters, viewsets

from apps.catalogs.models import ShippingLine
from apps.catalogs.serializers import ShippingLineSerializer


class ShippingLineViewSet(viewsets.ModelViewSet):
    queryset = ShippingLine.objects.select_related("group")
    serializer_class = ShippingLineSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name", "group__name"]
    ordering_fields = ["name", "code", "created_at"]
    ordering = ["name"]
