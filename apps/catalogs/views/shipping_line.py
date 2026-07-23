from django.db.models import Count, Prefetch
from django.db.models.deletion import ProtectedError
from rest_framework import filters, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

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

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            vessel_count = instance.vessels.count()
            booking_count = instance.bookings.count()
            parts = []
            if vessel_count:
                parts.append(
                    f"{vessel_count} barco{'s' if vessel_count != 1 else ''}"
                )
            if booking_count:
                parts.append(
                    f"{booking_count} reserva{'s' if booking_count != 1 else ''}"
                )
            linked = " y ".join(parts) if parts else "registros relacionados"
            return Response(
                {
                    "detail": (
                        f"No se puede eliminar la naviera porque tiene {linked} asociados. "
                        "Elimina o reasigna esos registros, o desactiva la naviera."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
