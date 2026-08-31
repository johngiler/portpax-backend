from django.db.models import Count, Prefetch, Q
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import DenyViewerWrites, user_port_ids
from apps.audit.models import LtaAuditEntry
from apps.audit.services.record import record_lta_audit
from apps.bookings.models import BookingStatus, LongTermAgreement
from apps.bookings.serializers.long_term_agreement import (
    LongTermAgreementDetailSerializer,
    LongTermAgreementSerializer,
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
from apps.bookings.tasks_lta import (
    lta_destroy_agreement,
    lta_generate_bookings,
    lta_link_matching,
    lta_regenerate_bookings,
    lta_resync_agreement,
)
from apps.bookings.services.lta.generate_bookings import (
    LtaGenerateError,
    validate_generate_prerequisites,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin


def _enqueue_user_id(request) -> int | None:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user.pk


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

    def get_serializer_class(self):
        if self.action == "retrieve":
            return LongTermAgreementDetailSerializer
        return LongTermAgreementSerializer

    queryset = LongTermAgreement.objects.select_related(
        "port",
        "shipping_line",
    ).prefetch_related("vessels", "positions")

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            linked_bookings_count=Count(
                "bookings",
                filter=~Q(bookings__status=BookingStatus.C),
                distinct=True,
            ),
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
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                Prefetch(
                    "audit_entries",
                    queryset=LtaAuditEntry.objects.select_related("actor").order_by(
                        "-created_at"
                    ),
                ),
            )
        return qs

    def perform_create(self, serializer):
        agreement = serializer.save()
        agreement = (
            LongTermAgreement.objects.select_related("port", "shipping_line")
            .prefetch_related("vessels", "positions")
            .get(pk=agreement.pk)
        )
        snap = snapshot_lta(agreement)
        async_result = lta_link_matching.delay(
            agreement.pk,
            _enqueue_user_id(self.request),
        )
        record_lta_audit(
            action="created",
            summary=f"Creó el acuerdo {snap['code']} (vinculación en cola)",
            agreement=agreement,
            changes={
                "created": snap,
                "job_status": "queued",
                "job_kind": "link",
                "task_id": async_result.id,
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
        async_result = lta_resync_agreement.delay(
            agreement.pk,
            _enqueue_user_id(self.request),
        )
        changes["job_status"] = "queued"
        changes["job_kind"] = "resync"
        changes["task_id"] = async_result.id
        record_lta_audit(
            action="updated",
            summary=f"Modificó el acuerdo {after['code']} (re-sincronización en cola)",
            agreement=agreement,
            changes=changes,
            actor=self.request.user,
            request=self.request,
            entity=after,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        snap = snapshot_lta(instance)
        async_result = lta_destroy_agreement.delay(
            instance.pk,
            _enqueue_user_id(request),
        )
        record_lta_audit(
            action="deleted",
            summary=f"Eliminación en cola: {snap['code']}",
            agreement=instance,
            agreement_code=snap["code"],
            agreement_name=snap["name"],
            port_id=snap.get("port_id"),
            port_code=snap.get("port_code") or "",
            shipping_line_code=snap.get("shipping_line_code") or "",
            changes={
                "deleted": snap,
                "job_status": "queued",
                "job_kind": "destroy",
                "task_id": async_result.id,
            },
            actor=request.user,
            request=request,
            entity=snap,
        )
        return Response(
            {
                "detail": "Eliminación en cola; la desvinculación corre en segundo plano.",
                "task_id": async_result.id,
                "agreement_id": instance.pk,
            },
            status=status.HTTP_202_ACCEPTED,
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

        allowed = user_port_ids(request.user)
        agreement_id_raw = request.query_params.get("agreement_id")
        agreement_id = None
        if agreement_id_raw not in (None, ""):
            try:
                agreement_id = int(agreement_id_raw)
            except (TypeError, ValueError):
                agreement_id = None
        data = build_lta_activity(
            allowed_ports=None if allowed is None else list(allowed),
            kind=request.query_params.get("kind") or "all",
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
            actor=request.query_params.get("actor"),
            agreement_id=agreement_id,
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
        """Enqueue linking of unmatched bookings that this LTA covers."""
        agreement = self.get_object()
        async_result = lta_link_matching.delay(
            agreement.pk,
            _enqueue_user_id(request),
        )
        record_lta_audit(
            action="link_bookings",
            summary=f"Vinculación en cola para {agreement.code}",
            agreement=agreement,
            changes={
                "job_status": "queued",
                "job_kind": "link",
                "task_id": async_result.id,
                "agreement_code": agreement.code,
            },
            actor=request.user,
            request=request,
            entity=snapshot_lta(agreement),
        )
        return Response(
            {
                "detail": "Vinculación en cola.",
                "task_id": async_result.id,
                "agreement_code": agreement.code,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def _enqueue_generate(self, request, *, regenerate: bool):
        agreement = self.get_object()
        try:
            validate_generate_prerequisites(agreement)
        except LtaGenerateError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        task = lta_regenerate_bookings if regenerate else lta_generate_bookings
        job_kind = "regenerate" if regenerate else "generate"
        label = "Regeneración" if regenerate else "Generación"
        async_result = task.delay(agreement.pk, _enqueue_user_id(request))
        record_lta_audit(
            action="generate_bookings",
            summary=f"{label} en cola para {agreement.code}",
            agreement=agreement,
            changes={
                "job_status": "queued",
                "job_kind": job_kind,
                "task_id": async_result.id,
                "agreement_code": agreement.code,
            },
            actor=request.user,
            request=request,
            entity=snapshot_lta(agreement),
        )
        return Response(
            {
                "detail": f"{label} en cola; corre en segundo plano.",
                "task_id": async_result.id,
                "agreement_code": agreement.code,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="generate-bookings")
    def generate_bookings(self, request, pk=None):
        """Enqueue materialization of LTA-status bookings (A1 dates × positions)."""
        return self._enqueue_generate(request, regenerate=False)

    @action(detail=True, methods=["post"], url_path="regenerate-bookings")
    def regenerate_bookings(self, request, pk=None):
        """Enqueue resync set-diff + materialize missing LTA slots."""
        return self._enqueue_generate(request, regenerate=True)
