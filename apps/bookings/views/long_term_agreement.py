from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import DenyViewerWrites
from apps.bookings.models import LongTermAgreement
from apps.bookings.serializers.long_term_agreement import LongTermAgreementSerializer
from apps.bookings.services.lta.link_bookings import link_matching_bookings
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
    ordering_fields = ["code", "name", "created_at", "valid_from"]
    ordering = ["port__name", "shipping_line__name", "code"]

    queryset = LongTermAgreement.objects.select_related(
        "port",
        "shipping_line",
    ).prefetch_related("vessels", "positions")

    def get_queryset(self):
        qs = super().get_queryset()
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

    @action(detail=True, methods=["post"], url_path="link-bookings")
    def link_bookings(self, request, pk=None):
        """Link existing unmatched bookings that this LTA covers."""
        agreement = self.get_object()
        result = link_matching_bookings(agreement, user=request.user)
        return Response(result, status=status.HTTP_200_OK)
