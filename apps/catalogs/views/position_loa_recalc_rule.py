from rest_framework import viewsets

from apps.catalogs.models import PositionLoaRecalcRule
from apps.catalogs.serializers.position_loa_recalc_rule import (
    PositionLoaRecalcRuleSerializer,
)
from apps.catalogs.services.port_catalog_audit import (
    diff_loa_recalc_rule_snapshots,
    loa_recalc_rule_audit_entity,
    snapshot_loa_recalc_rule,
)
from apps.catalogs.views.mixins import UserPortScopedQuerysetMixin
from apps.catalogs.views.port_catalog_audit_mixin import PortCatalogAuditMixin


class PositionLoaRecalcRuleViewSet(
    PortCatalogAuditMixin,
    UserPortScopedQuerysetMixin,
    viewsets.ModelViewSet,
):
    queryset = PositionLoaRecalcRule.objects.select_related(
        "port",
        "position_a",
        "position_b",
    )
    serializer_class = PositionLoaRecalcRuleSerializer
    port_access_field = "port_id"
    port_audit_resource = "loa_recalc_rule"
    port_audit_label = "la regla de eslora"

    def get_port_audit_snapshot(self, instance):
        if not hasattr(instance, "position_a"):
            instance = PositionLoaRecalcRule.objects.select_related(
                "port",
                "position_a",
                "position_b",
            ).get(pk=instance.pk)
        return snapshot_loa_recalc_rule(instance)

    def get_port_audit_diff(self, before, after):
        return diff_loa_recalc_rule_snapshots(before, after)

    def get_port_audit_entity(self, snap):
        return loa_recalc_rule_audit_entity(snap)

    def get_port_audit_identifier(self, snap):
        return f"{snap.get('position_a_code')}↔{snap.get('position_b_code')}"

    def get_queryset(self):
        qs = super().get_queryset()
        port_id = self.request.query_params.get("port")
        if port_id:
            qs = qs.filter(port_id=port_id)
        return qs
