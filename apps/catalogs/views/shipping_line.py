from django.db.models import Count, Prefetch
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import DenyViewerWrites, IsFrontendAppUser
from apps.audit.models import ShippingLineAuditEntry
from apps.audit.services.record import record_shipping_line_audit
from apps.catalogs.models import ShippingLine, Vessel
from apps.catalogs.serializers import ShippingLineDetailSerializer, ShippingLineSerializer
from apps.catalogs.services.shipping_line_activity import (
    build_shipping_line_activity,
    list_shipping_line_activity_actors,
)
from apps.catalogs.services.shipping_line_audit import (
    diff_shipping_line_snapshots,
    snapshot_shipping_line,
)
from apps.catalogs.services.shipping_line_export import (
    build_shipping_lines_csv_zip,
    build_shipping_lines_xlsx,
)
from apps.catalogs.services.shipping_line_import import (
    ShippingLineImportError,
    import_shipping_lines_workbook,
)


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
            vessel_count=Count("vessels", distinct=True),
        )
        group_id = self.request.query_params.get("group")
        if group_id:
            base = base.filter(group_id=group_id)
        if self.action == "retrieve":
            return base.prefetch_related(
                Prefetch("vessels", queryset=vessels_qs),
                Prefetch(
                    "audit_entries",
                    queryset=ShippingLineAuditEntry.objects.select_related(
                        "actor"
                    ).order_by("-created_at"),
                ),
            )
        return base

    def perform_create(self, serializer):
        line = serializer.save()
        line = ShippingLine.objects.select_related("group").get(pk=line.pk)
        snap = snapshot_shipping_line(line)
        record_shipping_line_audit(
            action="created",
            summary=f"Creó la naviera {snap['code']}",
            shipping_line=line,
            changes={"created": snap},
            actor=self.request.user,
            request=self.request,
            entity=snap,
        )

    def perform_update(self, serializer):
        before = snapshot_shipping_line(
            ShippingLine.objects.select_related("group").get(pk=serializer.instance.pk)
        )
        line = serializer.save()
        line = ShippingLine.objects.select_related("group").get(pk=line.pk)
        after = snapshot_shipping_line(line)
        changes = diff_shipping_line_snapshots(before, after)
        if changes:
            record_shipping_line_audit(
                action="updated",
                summary=f"Modificó la naviera {after['code']}",
                shipping_line=line,
                changes=changes,
                actor=self.request.user,
                request=self.request,
                entity=after,
            )

    def perform_destroy(self, instance):
        line = ShippingLine.objects.select_related("group").get(pk=instance.pk)
        snap = snapshot_shipping_line(line)
        instance.delete()
        record_shipping_line_audit(
            action="deleted",
            summary=f"Eliminó la naviera {snap['code']}",
            shipping_line=None,
            shipping_line_code=snap["code"],
            shipping_line_name=snap["name"],
            group_name=snap.get("group_name") or "",
            changes={"deleted": snap},
            actor=self.request.user,
            request=self.request,
            entity=snap,
        )

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

    @action(detail=False, methods=["get"], url_path="activity")
    def activity(self, request):
        try:
            page = int(request.query_params.get("page") or 1)
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.query_params.get("page_size") or 20)
        except (TypeError, ValueError):
            page_size = 20

        shipping_line_id_raw = request.query_params.get("shipping_line_id")
        shipping_line_id = None
        if shipping_line_id_raw not in (None, ""):
            try:
                shipping_line_id = int(shipping_line_id_raw)
            except (TypeError, ValueError):
                shipping_line_id = None

        data = build_shipping_line_activity(
            operation=request.query_params.get("operation") or "all",
            kind=request.query_params.get("kind"),
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
            actor=request.query_params.get("actor"),
            shipping_line_id=shipping_line_id,
            page=page,
            page_size=page_size,
        )
        return Response(data)

    @action(detail=False, methods=["get"], url_path="activity-actors")
    def activity_actors(self, request):
        return Response(list_shipping_line_activity_actors())

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        """Download grupos + navieras + barcos (xlsx three sheets, or csv zip).

        Query param is `export_format` (not `format`) — DRF reserves `format`.
        Applies the same list filters (search, group) to navieras/barcos;
        the Grupos sheet is always the full group catalog.
        """
        fmt = (request.query_params.get("export_format") or "xlsx").lower()
        if fmt not in ("xlsx", "csv"):
            return Response(
                {"detail": "export_format debe ser xlsx o csv."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lines_qs = self.filter_queryset(self.get_queryset())
        if not lines_qs.exists():
            return Response(
                {"detail": "No hay navieras para exportar con los filtros aplicados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stamp = timezone.localdate().isoformat()
        if fmt == "csv":
            content = build_shipping_lines_csv_zip(lines_qs)
            response = HttpResponse(content, content_type="application/zip")
            response["Content-Disposition"] = (
                f'attachment; filename="navieras_barcos_{stamp}.zip"'
            )
            return response

        content = build_shipping_lines_xlsx(lines_qs)
        response = HttpResponse(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = (
            f'attachment; filename="navieras_barcos_{stamp}.xlsx"'
        )
        return response

    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        permission_classes=[IsAuthenticated, IsFrontendAppUser, DenyViewerWrites],
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_catalog(self, request):
        """Upsert grupos + navieras + barcos from the exported Excel workbook."""
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"detail": "Adjunta un archivo Excel (.xlsx) en el campo «file»."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        name = (getattr(upload, "name", "") or "").lower()
        if not (name.endswith(".xlsx") or name.endswith(".xlsm")):
            return Response(
                {"detail": "Solo se acepta Excel (.xlsx). Usa el archivo exportado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = import_shipping_lines_workbook(
                upload,
                actor=request.user,
                request=request,
            )
        except ShippingLineImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)
