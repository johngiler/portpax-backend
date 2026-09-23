from django.db.models import Count
from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import DenyViewerWrites
from apps.bookings.models import Booking, BookingTag
from apps.bookings.serializers.booking_tag import BookingTagSerializer


class BookingTagViewSet(viewsets.ModelViewSet):
    """CRUD for reusable booking operator tags."""

    queryset = BookingTag.objects.annotate(booking_count=Count("bookings"))
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
        # History batches keep a snapshot FK (SET_NULL on delete). They must
        # not block removal once no booking still uses the tag.
        if Booking.objects.filter(tag=tag).exists():
            return Response(
                {
                    "detail": "No se puede eliminar: el tag está asociado a reservas.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)
