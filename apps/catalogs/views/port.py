from django.db.models import Count, Prefetch
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import user_port_ids
from apps.audit.services.record import record_port_audit
from apps.catalogs.models import Berth, Port, Position
from apps.catalogs.serializers import PortDetailSerializer, PortSerializer
from apps.catalogs.services.port_activity import build_port_activity
from apps.catalogs.services.port_audit import diff_port_snapshots, snapshot_port
from apps.catalogs.utils.port_scope import filter_qs_for_user_ports


class PortViewSet(viewsets.ModelViewSet):
    serializer_class = PortSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name", "commercial_name", "country"]
    ordering_fields = ["name", "code", "country", "created_at"]
    ordering = ["name"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PortDetailSerializer
        return PortSerializer

    def get_queryset(self):
        base = Port.objects.annotate(position_count=Count("positions"))
        base = filter_qs_for_user_ports(base, self.request.user, "id")
        if self.action == "retrieve":
            positions_qs = Position.objects.prefetch_related(
                "images",
                "bollard_lines__port_bollard",
                "fender_lines__port_fender",
            ).order_by(
                "sort_order", "code"
            )
            berths_qs = Berth.objects.prefetch_related("images").order_by("sort_order", "code")
            return base.prefetch_related(
                Prefetch("berths", queryset=berths_qs),
                Prefetch("positions", queryset=positions_qs),
                "bollards",
                "fenders",
                "images",
            )
        return base.prefetch_related("positions")

    def perform_create(self, serializer):
        port = serializer.save()
        snap = snapshot_port(port)
        record_port_audit(
            action="created",
            summary=f"Creó el puerto {snap['code']}",
            port=port,
            changes={"created": snap},
            actor=self.request.user,
            request=self.request,
            entity=snap,
        )

    def perform_update(self, serializer):
        before = snapshot_port(serializer.instance)
        port = serializer.save()
        after = snapshot_port(port)
        changes = diff_port_snapshots(before, after)
        if changes:
            record_port_audit(
                action="updated",
                summary=f"Modificó el puerto {after['code']}",
                port=port,
                changes=changes,
                actor=self.request.user,
                request=self.request,
                entity=after,
            )

    def perform_destroy(self, instance):
        snap = snapshot_port(instance)
        record_port_audit(
            action="deleted",
            summary=f"Eliminó el puerto {snap['code']}",
            port=None,
            port_code=snap["code"],
            port_name=snap["name"],
            subject_port_id=snap["id"],
            changes={"deleted": snap},
            actor=self.request.user,
            request=self.request,
            entity=snap,
        )
        instance.delete()

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

        allowed = user_port_ids(request.user)
        data = build_port_activity(
            allowed_ports=None if allowed is None else list(allowed),
            kind=request.query_params.get("kind") or "all",
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
            page=page,
            page_size=page_size,
        )
        return Response(data)
