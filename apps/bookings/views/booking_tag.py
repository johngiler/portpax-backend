from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import DenyViewerWrites
from apps.bookings.models import Booking, BookingImportBatch, BookingRunBatch, BookingTag
from apps.bookings.serializers.booking_tag import BookingTagSerializer


class BookingTagViewSet(viewsets.ModelViewSet):
    """CRUD for reusable booking operator tags."""

    queryset = BookingTag.objects.all()
    serializer_class = BookingTagSerializer
    permission_classes = [IsAuthenticated, DenyViewerWrites]
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        tag = self.get_object()
        still_used = (
            Booking.objects.filter(tag=tag).exists()
            or BookingImportBatch.objects.filter(tag=tag).exists()
            or BookingRunBatch.objects.filter(tag=tag).exists()
        )
        if still_used:
            return Response(
                {
                    "detail": "No se puede eliminar: el tag está asociado a reservas o lotes.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)
