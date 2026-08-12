from rest_framework import viewsets

from apps.catalogs.models import PositionLoaRecalcRule
from apps.catalogs.serializers.position_loa_recalc_rule import (
    PositionLoaRecalcRuleSerializer,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin


class PositionLoaRecalcRuleViewSet(UserPortScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = PositionLoaRecalcRule.objects.select_related(
        "port",
        "combined_position",
    ).prefetch_related("combined_position__component_links__source_position")
    serializer_class = PositionLoaRecalcRuleSerializer
    port_access_field = "port_id"

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
