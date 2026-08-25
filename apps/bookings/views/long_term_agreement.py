from django.db.models import Count
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import DenyViewerWrites, user_port_ids
from apps.audit.services.record import record_lta_audit
from apps.bookings.models import LongTermAgreement
from apps.bookings.serializers.long_term_agreement import LongTermAgreementSerializer
from apps.bookings.services.lta.link_bookings import (
    link_matching_bookings,
    resync_agreement_bookings,
    unlink_agreement_bookings,
)
from apps.bookings.services.lta.windows import windows_as_dict
from apps.bookings.services.lta.lta_activity import (
    build_lta_activity,
    list_lta_activity_actors,
)
from apps.bookings.services.lta.lta_audit import (
    diff_lta_snapshots,
    snapshot_lta,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin


class LongTermAgreementViewSet(UserPortScopedQuerysetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, DenyViewerWrites]
    serializer_class = LongTermAgreementSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    port_access_field = "port_id"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "code",
        "name",
        "port__code",
        "port__name",
        "shipping_line__code",
        "shipping_line__name",
    ]
    ordering_fields = ["code", "name", "created_at", "valid_from", "linked_bookings_count"]
    ordering = ["port__name", "shipping_line__name", "code"]

    queryset = LongTermAgreement.objects.select_related(
        "port",
        "shipping_line",
    ).prefetch_related("vessels", "positions")

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            linked_bookings_count=Count("bookings", distinct=True),
        )
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        line_id = self.request.query_params.get("shipping_line")
        if line_id:
            qs = qs.filter(shipping_line_id=line_id)
        active = self.request.query_params.get("is_active")
        if active is not None and active != "":
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs

    def perform_create(self, serializer):
        agreement = serializer.save()
        agreement = (
            LongTermAgreement.objects.select_related("port", "shipping_line")
            .prefetch_related("vessels", "positions")
            .get(pk=agreement.pk)
        )
        snap = snapshot_lta(agreement)
        link_result = link_matching_bookings(agreement, user=self.request.user)
        record_lta_audit(
            action="created",
            summary=f"Creó el acuerdo {snap['code']}",
            agreement=agreement,
            changes={
                "created": snap,
                "linked_bookings": int(link_result.get("linked") or 0),
            },
            actor=self.request.user,
            request=self.request,
            entity=snap,
        )

    def perform_update(self, serializer):
        before = snapshot_lta(serializer.instance)
        agreement = serializer.save()
        agreement = (
            LongTermAgreement.objects.select_related("port", "shipping_line")
            .prefetch_related("vessels", "positions")
            .get(pk=agreement.pk)
        )
        after = snapshot_lta(agreement)
        changes = diff_lta_snapshots(before, after)
        # Unlink current FKs, then re-link under the saved rules.
        sync = resync_agreement_bookings(agreement, user=self.request.user)
        changes["unlinked_bookings"] = int(sync.get("unlinked") or 0)
        changes["linked_bookings"] = int(sync.get("linked") or 0)
        record_lta_audit(
            action="updated",
            summary=f"Modificó el acuerdo {after['code']}",
            agreement=agreement,
            changes=changes,
            actor=self.request.user,
            request=self.request,
            entity=after,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        snap = snapshot_lta(instance)
        unlink = unlink_agreement_bookings(instance, user=self.request.user)
        record_lta_audit(
            action="deleted",
            summary=f"Eliminó el acuerdo {snap['code']}",
            agreement=None,
            agreement_code=snap["code"],
            agreement_name=snap["name"],
            port_id=snap.get("port_id"),
            port_code=snap.get("port_code") or "",
            shipping_line_code=snap.get("shipping_line_code") or "",
            changes={
                "deleted": snap,
                "unlinked_bookings": int(unlink.get("unlinked") or 0),
            },
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
        data = build_lta_activity(
            allowed_ports=None if allowed is None else list(allowed),
            kind=request.query_params.get("kind") or "all",
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
            actor=request.query_params.get("actor"),
            page=page,
            page_size=page_size,
        )
        return Response(data)

    @action(detail=False, methods=["get"], url_path="activity-actors")
    def activity_actors(self, request):
        allowed = user_port_ids(request.user)
        return Response(
            list_lta_activity_actors(
                allowed_ports=None if allowed is None else list(allowed),
            )
        )

    @action(detail=False, methods=["get"], url_path="windows")
    def windows(self, request):
        """Rolling 6-month blockcitos: current, open booking, LTA zone."""
        return Response(windows_as_dict())

    @action(detail=True, methods=["post"], url_path="link-bookings")
    def link_bookings(self, request, pk=None):
        """Link existing unmatched bookings that this LTA covers."""
        agreement = self.get_object()
        result = link_matching_bookings(agreement, user=request.user)
        linked = int(result.get("linked") or 0)
        skipped = int(result.get("skipped") or 0)
        record_lta_audit(
            action="link_bookings",
            summary=(
                f"Vinculó reservas al acuerdo {agreement.code}: "
                f"{linked} vinculadas, {skipped} omitidas"
            ),
            agreement=agreement,
            changes={
                "linked": linked,
                "skipped": skipped,
                "agreement_code": result.get("agreement_code") or agreement.code,
            },
            actor=request.user,
            request=request,
            entity=snapshot_lta(agreement),
        )
        return Response(result, status=status.HTTP_200_OK)
