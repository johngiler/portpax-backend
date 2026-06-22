from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.bookings.models import Booking
from apps.bookings.serializers import (
    BookingBatchCreateSerializer,
    BookingSerializer,
    BookingStatusUpdateSerializer,
)
from apps.bookings.services.booking import BookingBatchCreateError, create_booking_batch


class BookingViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "booking_code",
        "port__name",
        "port__code",
        "shipping_line__name",
        "vessel__name",
    ]
    ordering_fields = ["call_date", "created_at", "booking_code", "status"]
    ordering = ["-call_date", "-created_at"]
    http_method_names = ["get", "patch", "head", "options", "post"]

    def get_queryset(self):
        qs = Booking.objects.select_related("port", "shipping_line", "vessel")
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        shipping_line_id = self.request.query_params.get("shipping_line")
        if shipping_line_id:
            qs = qs.filter(shipping_line_id=shipping_line_id)
        vessel_id = self.request.query_params.get("vessel")
        if vessel_id:
            qs = qs.filter(vessel_id=vessel_id)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return BookingStatusUpdateSerializer
        return BookingSerializer

    def partial_update(self, request, *args, **kwargs):
        booking = self.get_object()
        serializer = self.get_serializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        return Response(BookingSerializer(booking, context={"request": request}).data)

    @action(detail=False, methods=["post"], url_path="batch")
    def batch_create(self, request):
        serializer = BookingBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            bookings = create_booking_batch(
                port_id=data["port"],
                shipping_line_id=data["shipping_line"],
                vessel_id=data["vessel"],
                call_dates=data["call_dates"],
                notes=data.get("notes", ""),
                created_by=request.user,
            )
        except BookingBatchCreateError as exc:
            payload = {"detail": str(exc)}
            if exc.field:
                payload = {exc.field: [str(exc)]}
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            BookingSerializer(bookings, many=True, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
