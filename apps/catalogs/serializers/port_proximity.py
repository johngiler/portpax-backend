from rest_framework import serializers

from apps.catalogs.models import PortProximity


class PortProximitySerializer(serializers.ModelSerializer):
    from_port_name = serializers.CharField(source="from_port.name", read_only=True)
    to_port_name = serializers.CharField(source="to_port.name", read_only=True)

    class Meta:
        model = PortProximity
        fields = [
            "from_port",
            "from_port_name",
            "to_port",
            "to_port_name",
            "distance_km",
            "travel_hours_min",
            "speed_knots_used",
        ]
        read_only_fields = fields

