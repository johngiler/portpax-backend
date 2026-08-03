from django.db.models import Count, Prefetch
from django.db.models.deletion import ProtectedError
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.services.record import record_shipping_line_audit
from apps.catalogs.models import ShippingLine, Vessel
from apps.catalogs.serializers import ShippingLineDetailSerializer, ShippingLineSerializer
from apps.catalogs.services.shipping_line_activity import build_shipping_line_activity
from apps.catalogs.services.shipping_line_audit import (
    diff_shipping_line_snapshots,
    snapshot_shipping_line,
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
            vessel_count=Count("vessels"),
        )
        group_id = self.request.query_params.get("group")
        if group_id:
            base = base.filter(group_id=group_id)
        if self.action == "retrieve":
            return base.prefetch_related(Prefetch("vessels", queryset=vessels_qs))
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

        data = build_shipping_line_activity(
            kind=request.query_params.get("kind") or "all",
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
            page=page,
            page_size=page_size,
        )
        return Response(data)
