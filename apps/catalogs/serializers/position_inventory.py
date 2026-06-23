from rest_framework import serializers

from apps.catalogs.models import PortBollard, PortFender, PositionBollardLine, PositionFenderLine


class PositionBollardAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PositionBollardLine
        fields = ["port_bollard", "quantity"]


class PositionFenderAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PositionFenderLine
        fields = ["port_fender", "quantity"]
