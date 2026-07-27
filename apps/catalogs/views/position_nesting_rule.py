from rest_framework import viewsets

from apps.catalogs.models import PositionNestingRule
from apps.catalogs.serializers.position_nesting_rule import (
    PositionNestingRuleSerializer,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin


class PositionNestingRuleViewSet(UserPortScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = PositionNestingRule.objects.select_related(
        "port",
        "outer_position",
        "inner_position",
    )
    serializer_class = PositionNestingRuleSerializer
    port_access_field = "port_id"

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
