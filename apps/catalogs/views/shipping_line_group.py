from rest_framework import filters, viewsets

from apps.catalogs.models import ShippingLineGroup
from apps.catalogs.serializers import ShippingLineGroupSerializer


class ShippingLineGroupViewSet(viewsets.ModelViewSet):
    queryset = ShippingLineGroup.objects.all()
    serializer_class = ShippingLineGroupSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name"]
    ordering_fields = ["name", "code", "created_at"]
    ordering = ["name"]
