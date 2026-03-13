"""
Serializers para la API de Docking/Muellaje.
"""
from rest_framework import serializers

from .models import Berth, Port, Scale, Ship, ShippingLine


class ShippingLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingLine
        fields = ["id", "name", "code"]


class PortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Port
        fields = ["id", "name", "code"]


class BerthSerializer(serializers.ModelSerializer):
    port_name = serializers.CharField(source="port.name", read_only=True)

    class Meta:
        model = Berth
        fields = ["id", "port", "port_name", "name", "capacity_pax", "max_draft_m", "max_length_m"]


class ShipSerializer(serializers.ModelSerializer):
    shipping_line_name = serializers.CharField(source="shipping_line.name", read_only=True)

    class Meta:
        model = Ship
        fields = [
            "id", "shipping_line", "shipping_line_name",
            "name", "imo", "capacity_pax", "length_m", "draft_m",
        ]


class ScaleSerializer(serializers.ModelSerializer):
    ship_name = serializers.CharField(source="ship.name", read_only=True)
    port_name = serializers.CharField(source="port.name", read_only=True)
    berth_name = serializers.CharField(source="berth.name", read_only=True)

    class Meta:
        model = Scale
        fields = [
            "id", "ship", "ship_name", "port", "port_name",
            "berth", "berth_name", "date", "pax_count", "crew_count",
        ]
