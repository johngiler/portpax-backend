from django.db.models import Count, Prefetch
from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.catalogs.models import ShippingLine, Vessel
from apps.catalogs.serializers import ShippingLineDetailSerializer, ShippingLineSerializer


class ShippingLineViewSet(viewsets.ModelViewSet):
    serializer_class = ShippingLineSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name", "group__name", "vessels__name"]
    ordering_fields = ["name", "code", "created_at"]
    ordering = ["name"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ShippingLineDetailSerializer
        return ShippingLineSerializer

    def get_queryset(self):
        vessels_qs = Vessel.objects.order_by("name")
        base = ShippingLine.objects.select_related("group").annotate(
            vessel_count=Count("vessels"),
        )
        group_id = self.request.query_params.get("group")
        if group_id:
            base = base.filter(group_id=group_id)
        if self.action == "retrieve":
            return base.prefetch_related(Prefetch("vessels", queryset=vessels_qs))
        return base
