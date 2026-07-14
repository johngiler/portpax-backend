from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.mixins import (
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.bookings.models import Booking, BookingStatus
from apps.bookings.serializers import (
    BookingBatchCreateSerializer,
    BookingSerializer,
    BookingUpdateSerializer,
    BookingValidateSerializer,
)
from apps.bookings.services.booking import (
    BookingBatchCreateError,
    BookingDeleteError,
    create_booking_batch,
    delete_cancelled_booking,
)
from apps.bookings.services.booking_export import build_bookings_csv, build_bookings_xlsx
from apps.bookings.services.validation import suggest_positions
from apps.bookings.utils.list_ordering import apply_booking_list_ordering


class BookingViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter]
    search_fields = [
        "booking_code",
        "port__name",
        "port__code",
        "shipping_line__name",
        "vessel__name",
    ]
    http_method_names = ["get", "patch", "delete", "head", "options", "post"]

    def get_queryset(self):
        qs = Booking.objects.select_related(
            "port",
            "shipping_line",
            "vessel",
            "position",
        ).prefetch_related("audit_entries")
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
        if status_param == "completed":
            qs = qs.filter(
                call_date__lt=timezone.localdate(),
                status__in=[BookingStatus.REQUESTED, BookingStatus.CONFIRMED],
            )
        elif status_param:
            qs = qs.filter(status=status_param)
        call_date_from = self.request.query_params.get("call_date_from")
        if call_date_from:
            qs = qs.filter(call_date__gte=call_date_from)
        call_date_to = self.request.query_params.get("call_date_to")
        if call_date_to:
            qs = qs.filter(call_date__lte=call_date_to)
        ordering = self.request.query_params.get("ordering", "call_date_proximity")
        return apply_booking_list_ordering(qs, ordering)

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return BookingUpdateSerializer
        if self.action == "validate":
            return BookingValidateSerializer
        return BookingSerializer

    def partial_update(self, request, *args, **kwargs):
        booking = self.get_object()
        serializer = self.get_serializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        return Response(BookingSerializer(booking, context={"request": request}).data)

    def destroy(self, request, *args, **kwargs):
        booking = self.get_object()
        try:
            delete_cancelled_booking(booking)
        except BookingDeleteError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

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

    @action(detail=False, methods=["post"], url_path="validate")
    def validate(self, request):
        serializer = BookingValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result)

    @action(detail=False, methods=["get"], url_path="suggest-positions")
    def suggest_positions(self, request):
        port_id = request.query_params.get("port")
        vessel_id = request.query_params.get("vessel")
        call_date = request.query_params.get("call_date")
        if not port_id or not vessel_id or not call_date:
            return Response(
                {"detail": "Se requieren port, vessel y call_date."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from datetime import date

        try:
            parsed_date = date.fromisoformat(call_date)
        except ValueError:
            return Response(
                {"detail": "call_date debe ser ISO (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggestions = suggest_positions(int(port_id), int(vessel_id), parsed_date)
        return Response({"positions": suggestions})

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        """Download bookings report (xlsx/csv) using the same filters as the list.

        Query param is `export_format` (not `format`) — DRF reserves `format`
        for content negotiation and returns 404 for unknown suffixes like xlsx.
        """
        fmt = (request.query_params.get("export_format") or "xlsx").lower()
        if fmt not in ("xlsx", "csv"):
            return Response(
                {"detail": "export_format debe ser xlsx o csv."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bookings = list(self.filter_queryset(self.get_queryset()))
        if not bookings:
            return Response(
                {"detail": "No hay reservas para exportar con los filtros aplicados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stamp = timezone.localdate().isoformat()
        if fmt == "csv":
            content = build_bookings_csv(bookings)
            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="reservas_{stamp}.csv"'
            return response

        content = build_bookings_xlsx(bookings)
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="reservas_{stamp}.xlsx"'
        return response

    @action(detail=False, methods=["get"], url_path="dashboard-stats")
    def dashboard_stats(self, request):
        from datetime import date as date_cls

        from apps.bookings.services.dashboard_stats import build_dashboard_stats

        today = timezone.localdate()
        default_from = date_cls(today.year, 1, 1)
        default_to = date_cls(today.year, 12, 31)

        def parse_date(key: str, fallback: date_cls) -> date_cls | Response:
            raw = request.query_params.get(key)
            if not raw:
                return fallback
            try:
                return date_cls.fromisoformat(raw)
            except ValueError:
                return Response(
                    {"detail": f"{key} debe ser ISO (YYYY-MM-DD)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        date_from = parse_date("date_from", default_from)
        if isinstance(date_from, Response):
            return date_from
        date_to = parse_date("date_to", default_to)
        if isinstance(date_to, Response):
            return date_to

        def optional_int(key: str) -> int | None:
            raw = request.query_params.get(key)
            if not raw:
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        return Response(
            build_dashboard_stats(
                date_from=date_from,
                date_to=date_to,
                port_id=optional_int("port"),
                shipping_line_id=optional_int("shipping_line"),
                shipping_line_group_id=optional_int("shipping_line_group"),
            )
        )
