from rest_framework import serializers

from apps.bookings.services.booking.first_arrival import FIRST_ARRIVAL_STATUSES
from apps.catalogs.models import Vessel
from apps.core.serializers.mixins import WebPImageFieldsMixin


class VesselSerializer(WebPImageFieldsMixin, serializers.ModelSerializer):
    webp_image_fields = ("logo",)
    shipping_line_name = serializers.CharField(source="shipping_line.name", read_only=True)
    group_name = serializers.CharField(source="shipping_line.group.name", read_only=True)
    total_persons = serializers.SerializerMethodField()
    arrived_ports = serializers.SerializerMethodField()

    class Meta:
        model = Vessel
        fields = [
            "id",
            "shipping_line",
            "shipping_line_name",
            "group_name",
            "name",
            "ship_code",
            "logo",
            "vessel_class",
            "gross_tonnage",
            "pax_capacity",
            "crew_capacity",
            "total_persons",
            "loa_m",
            "beam_m",
            "draft_m",
            "flag",
            "year_built",
            "segment",
            "size_category",
            "mooring_line_count",
            "bollard_count",
            "bollard_swl_t",
            "is_active",
            "arrived_ports",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "total_persons",
            "arrived_ports",
            "created_at",
            "updated_at",
        ]

    def get_total_persons(self, obj: Vessel) -> int | None:
        return obj.total_persons

    def _port_logo_url(self, port) -> str | None:
        if not port or not getattr(port, "logo", None):
            return None
        try:
            url = port.logo.url
        except ValueError:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_arrived_ports(self, obj: Vessel) -> list[dict]:
        """Distinct ports with ≥1 CO/CL/R booking for this vessel (insignias)."""
        prefetched = getattr(obj, "_arrival_bookings", None)
        ports_by_id: dict[int, object] = {}
        if prefetched is not None:
            for booking in prefetched:
                port = getattr(booking, "port", None)
                if port is not None and port.pk not in ports_by_id:
                    ports_by_id[port.pk] = port
        else:
            from apps.catalogs.models import Port

            for port in (
                Port.objects.filter(
                    bookings__vessel_id=obj.pk,
                    bookings__status__in=FIRST_ARRIVAL_STATUSES,
                )
                .distinct()
                .only("id", "name", "country", "logo", "code")
            ):
                ports_by_id[port.pk] = port

        rows = [
            {
                "id": port.pk,
                "name": port.name,
                "country": port.country or "",
                "logo": self._port_logo_url(port),
            }
            for port in ports_by_id.values()
        ]
        rows.sort(key=lambda r: (r["name"] or "").lower())
        return rows
