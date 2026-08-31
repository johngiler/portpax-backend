from rest_framework import viewsets

from apps.catalogs.models import PositionNestingRule
from apps.catalogs.serializers.position_nesting_rule import (
    PositionNestingRuleSerializer,
)
from apps.catalogs.services.port_catalog_audit import (
    diff_nesting_rule_snapshots,
    nesting_rule_audit_entity,
    snapshot_nesting_rule,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class PositionNestingRuleViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = PositionNestingRule.objects.select_related(
        "port",
        "outer_position",
        "inner_position",
    )
    serializer_class = PositionNestingRuleSerializer
    port_access_field = "port_id"
    port_audit_resource = "nesting_rule"
    port_audit_label = "la regla de atraque"

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "outer_position"):
            instance = PositionNestingRule.objects.select_related(
                "port",
                "outer_position",
                "inner_position",
            ).get(pk=instance.pk)
        return snapshot_nesting_rule(instance)

    def get_port_audit_diff(self, before, after):
        return diff_nesting_rule_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return nesting_rule_audit_entity(snap)

    def get_port_audit_identifier(self, snap):
        return (
            f"{snap.get('outer_position_code')} → {snap.get('inner_position_code')}"
        )

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
