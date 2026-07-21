from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.mixins import (
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import DenyViewerWrites, user_can_access_port, user_port_ids
from apps.bookings.constants import ACTIVE_BOOKING_STATUSES
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
from apps.bookings.services.calendar_export import (
    build_calendar_csv,
    build_calendar_xlsx,
    calendar_export_filename,
)
from apps.bookings.services.operational_reports import (
    build_booking_totals,
    build_weekly_movements,
)
from apps.bookings.services.validation import suggest_positions
from apps.bookings.utils.list_ordering import apply_booking_list_ordering

_PORT_ACCESS_DENIED = "No tienes acceso a este puerto."


class BookingViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, DenyViewerWrites]
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

    def _ensure_port_access(self, port_id) -> None:
        if not user_can_access_port(self.request.user, int(port_id)):
            raise PermissionDenied(_PORT_ACCESS_DENIED)

    def get_queryset(self):
        qs = Booking.objects.select_related(
            "port",
            "shipping_line",
            "vessel",
            "position",
        ).prefetch_related("audit_entries")
        allowed_ports = user_port_ids(self.request.user)
        if allowed_ports is not None:
            qs = qs.filter(port_id__in=allowed_ports)
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
                Q(
                    call_date__lt=timezone.localdate(),
                    status__in=ACTIVE_BOOKING_STATUSES,
                )
                | Q(status=BookingStatus.R)
            )
        elif status_param == "action":
            # Dashboard “Requieren acción”: Hold + NR with call_date from today.
            qs = qs.filter(
                status__in=[BookingStatus.NR, BookingStatus.H],
                call_date__gte=timezone.localdate(),
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
        self._ensure_port_access(booking.port_id)
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
        self._ensure_port_access(data["port"])

        try:
            bookings = create_booking_batch(
                port_id=data["port"],
                shipping_line_id=data["shipping_line"],
                vessel_id=data["vessel"],
                call_dates=data["call_dates"],
                notes=data.get("notes", ""),
                created_by=request.user,
                eta=data.get("eta"),
                etd=data.get("etd"),
                planned_pax=data.get("planned_pax"),
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
        self._ensure_port_access(serializer.validated_data["port"])
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
        self._ensure_port_access(port_id)
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
                allowed_ports=user_port_ids(request.user),
                today=timezone.localdate(),
            )
        )

    def _parse_iso_date_param(self, key: str, required: bool = True):
        from datetime import date as date_cls

        raw = self.request.query_params.get(key)
        if not raw:
            if required:
                return None, Response(
                    {"detail": f"{key} es obligatorio (YYYY-MM-DD)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return None, None
        try:
            return date_cls.fromisoformat(raw), None
        except ValueError:
            return None, Response(
                {"detail": f"{key} debe ser ISO (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"], url_path="calendar-export")
    def calendar_export(self, request):
        """Export operational calendar rows for one or more ports and a date range.

        `port` accepts a single id or a comma-separated list (one file).
        """
        port_raw = request.query_params.get("port")
        if not port_raw:
            return Response(
                {"detail": "port es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            port_ids = [int(part.strip()) for part in port_raw.split(",") if part.strip()]
        except (TypeError, ValueError):
            return Response(
                {"detail": "port inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not port_ids:
            return Response(
                {"detail": "port es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for port_id in port_ids:
            self._ensure_port_access(port_id)

        date_from, err = self._parse_iso_date_param("call_date_from")
        if err:
            return err
        date_to, err = self._parse_iso_date_param("call_date_to")
        if err:
            return err

        fmt = (request.query_params.get("export_format") or "xlsx").lower()
        if fmt not in ("xlsx", "csv"):
            return Response(
                {"detail": "export_format debe ser xlsx o csv."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Do not use get_queryset()'s single-port filter (port may be "1,2,3").
        qs = Booking.objects.select_related(
            "port",
            "shipping_line",
            "vessel",
            "position",
        )
        allowed_ports = user_port_ids(request.user)
        if allowed_ports is not None:
            qs = qs.filter(port_id__in=allowed_ports)
        qs = qs.filter(
            port_id__in=port_ids,
            call_date__gte=date_from,
            call_date__lte=date_to,
        ).order_by(
            "port__name",
            "call_date",
            "position__sort_order",
            "vessel__name",
        )
        shipping_line_id = request.query_params.get("shipping_line")
        if shipping_line_id:
            qs = qs.filter(shipping_line_id=shipping_line_id)
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        bookings = list(qs)
        if not bookings:
            return Response(
                {"detail": "No hay reservas para exportar en ese rango."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        seen: list[str] = []
        for booking in bookings:
            code = booking.port.code
            if code not in seen:
                seen.append(code)
        filename = calendar_export_filename(seen, date_from, date_to, fmt)
        if fmt == "csv":
            content = build_calendar_csv(bookings)
            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        else:
            content = build_calendar_xlsx(bookings)
            response = HttpResponse(
                content,
                content_type=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
            )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=["get"], url_path="report-totals")
    def report_totals(self, request):
        date_from, err = self._parse_iso_date_param("date_from")
        if err:
            return err
        date_to, err = self._parse_iso_date_param("date_to")
        if err:
            return err

        def optional_int(key: str) -> int | None:
            raw = request.query_params.get(key)
            if not raw:
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        without_lta = (request.query_params.get("without_lta") or "").lower() in (
            "1",
            "true",
            "yes",
        )
        port_id = optional_int("port")
        if port_id is not None:
            self._ensure_port_access(port_id)

        return Response(
            build_booking_totals(
                date_from=date_from,
                date_to=date_to,
                port_id=port_id,
                shipping_line_id=optional_int("shipping_line"),
                without_lta=without_lta,
                allowed_ports=user_port_ids(request.user),
                request=request,
            )
        )

    @action(detail=False, methods=["get"], url_path="report-movements")
    def report_movements(self, request):
        date_from, err = self._parse_iso_date_param("date_from")
        if err:
            return err
        date_to, err = self._parse_iso_date_param("date_to")
        if err:
            return err

        port_id = None
        raw_port = request.query_params.get("port")
        if raw_port:
            try:
                port_id = int(raw_port)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "port inválido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            self._ensure_port_access(port_id)

        return Response(
            build_weekly_movements(
                date_from=date_from,
                date_to=date_to,
                port_id=port_id,
                allowed_ports=user_port_ids(request.user),
            )
        )
