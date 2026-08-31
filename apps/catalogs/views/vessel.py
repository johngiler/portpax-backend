from rest_framework import filters, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.audit.services.record import record_shipping_line_audit
from apps.catalogs.models import Vessel
from apps.catalogs.serializers import VesselSerializer
from apps.catalogs.services.vessel_audit import (
    diff_vessel_snapshots,
    snapshot_vessel,
    vessel_audit_entity,
)


class VesselViewSet(viewsets.ModelViewSet):
    queryset = Vessel.objects.select_related("shipping_line__group")
    serializer_class = VesselSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "name",
        "ship_code",
        "vessel_class",
        "shipping_line__name",
        "shipping_line__group__name",
    ]
    ordering_fields = ["name", "loa_m", "draft_m", "created_at"]
    ordering = ["name"]

    def _reload_vessel(self, vessel: Vessel) -> Vessel:
        return Vessel.objects.select_related("shipping_line__group").get(pk=vessel.pk)

    def perform_create(self, serializer):
        vessel = serializer.save()
        vessel = self._reload_vessel(vessel)
        snap = snapshot_vessel(vessel)
        line = vessel.shipping_line
        record_shipping_line_audit(
            action="vessel_created",
            summary=f"Creó el barco {snap['name']}",
            shipping_line=line,
            changes={"created": snap},
            entity=vessel_audit_entity(snap),
            actor=self.request.user,
            request=self.request,
        )

    def perform_update(self, serializer):
        before = snapshot_vessel(self._reload_vessel(serializer.instance))
        vessel = serializer.save()
        vessel = self._reload_vessel(vessel)
        after = snapshot_vessel(vessel)
        changes = diff_vessel_snapshots(before, after)
        if changes:
            line = vessel.shipping_line
            record_shipping_line_audit(
                action="vessel_updated",
                summary=f"Modificó el barco {after['name']}",
                shipping_line=line,
                changes=changes,
                entity=vessel_audit_entity(after),
                actor=self.request.user,
                request=self.request,
            )

    def perform_destroy(self, instance):
        vessel = self._reload_vessel(instance)
        snap = snapshot_vessel(vessel)
        line = vessel.shipping_line
        record_shipping_line_audit(
            action="vessel_deleted",
            summary=f"Eliminó el barco {snap['name']}",
            shipping_line=line,
            changes={"deleted": snap},
            entity=vessel_audit_entity(snap),
            actor=self.request.user,
            request=self.request,
        )
        instance.delete()

    def get_queryset(self):
        qs = super().get_queryset()
        shipping_line_id = self.request.query_params.get("shipping_line")
        if shipping_line_id:
            qs = qs.filter(shipping_line_id=shipping_line_id)
        group_id = (
            self.request.query_params.get("shipping_line_group")
            or self.request.query_params.get("group")
        )
        if group_id:
            qs = qs.filter(shipping_line__group_id=group_id)
        return qs
