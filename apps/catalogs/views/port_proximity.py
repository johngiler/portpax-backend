from __future__ import annotations

from rest_framework import permissions, viewsets

from apps.accounts.permissions import user_port_ids
from apps.catalogs.models import PortProximity
from apps.catalogs.serializers.port_proximity import PortProximitySerializer


class PortProximityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only access to the precomputed port proximity matrix.

    Query params (all optional):
    - from_port: filter by origin port id
    - to_port: filter by destination port id
    - within_hours: only edges with travel_hours_min <= within_hours
    - within_days: only edges with travel_hours_min <= within_days*24
    """

    serializer_class = PortProximitySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = (
            PortProximity.objects.select_related("from_port", "to_port")
            .all()
            .order_by("from_port_id", "to_port_id")
        )

        allowed = user_port_ids(self.request.user)
        if allowed is not None:
            qs = qs.filter(from_port_id__in=allowed, to_port_id__in=allowed)

        from_port = self.request.query_params.get("from_port")
        if from_port:
            qs = qs.filter(from_port_id=from_port)

        to_port = self.request.query_params.get("to_port")
        if to_port:
            qs = qs.filter(to_port_id=to_port)

        within_hours = self.request.query_params.get("within_hours")
        if within_hours:
            qs = qs.filter(travel_hours_min__lte=within_hours)

        within_days = self.request.query_params.get("within_days")
        if within_days:
            # days is coarse since booking call_date is date-only.
            qs = qs.filter(travel_hours_min__lte=int(within_days) * 24)

        return qs

