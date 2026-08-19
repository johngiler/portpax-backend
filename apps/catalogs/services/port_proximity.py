from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from apps.catalogs.models import Port, PortProximity


# Common hardcoded baseline speed to convert distance → minimum travel time.
# We keep it conservative so “impossible” close-to-day hops are caught.
DEFAULT_PORT_PROXIMITY_SPEED_KNOTS = Decimal("10.00")

EARTH_RADIUS_KM = Decimal("6371.0088")


def _d(value: Decimal | str | float) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def haversine_distance_km(
    lat1: Decimal,
    lon1: Decimal,
    lat2: Decimal,
    lon2: Decimal,
) -> Decimal:
    """
    Haversine distance between 2 points in km.

    Uses Decimal inputs because Port coordinates are stored as DecimalFields.
    """
    import math

    lat1_f = float(lat1)
    lon1_f = float(lon1)
    lat2_f = float(lat2)
    lon2_f = float(lon2)

    dlat = math.radians(lat2_f - lat1_f)
    dlon = math.radians(lon2_f - lon1_f)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1_f)) * math.cos(math.radians(lat2_f)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    dist_km = float(EARTH_RADIUS_KM) * c
    return Decimal(str(dist_km))


def travel_hours_min(
    distance_km: Decimal,
    *,
    speed_knots: Decimal = DEFAULT_PORT_PROXIMITY_SPEED_KNOTS,
) -> Decimal:
    """
    Minimum travel time in hours based on a constant cruise speed.

    knots → km/h:
      1 knot = 1.852 km/h
    """
    km_h = speed_knots * Decimal("1.852")
    if km_h <= 0:
        return Decimal("999999")
    hours = distance_km / km_h
    return hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def recalculate_all_port_proximity(*, speed_knots: Decimal = DEFAULT_PORT_PROXIMITY_SPEED_KNOTS) -> None:
    ports = list(
        Port.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False)
    )
    with transaction.atomic():
        PortProximity.objects.all().delete()
        _seed_pairs(ports, speed_knots=speed_knots)


def recalculate_port_proximity_for_port(
    port_id: int,
    *,
    speed_knots: Decimal = DEFAULT_PORT_PROXIMITY_SPEED_KNOTS,
) -> None:
    port = Port.objects.filter(pk=port_id, is_active=True).first()
    if port is None or port.latitude is None or port.longitude is None:
        return

    other_ports = list(
        Port.objects.filter(
            is_active=True,
            latitude__isnull=False,
            longitude__isnull=False,
        )
    )

    with transaction.atomic():
        PortProximity.objects.filter(from_port_id=port_id).delete()
        PortProximity.objects.filter(to_port_id=port_id).delete()
        # Rebuild both directions:
        # - port → others
        # - others → port
        _seed_pairs([port], other_ports, speed_knots=speed_knots)
        _seed_pairs(other_ports, [port], speed_knots=speed_knots)


def _seed_pairs(
    ports_a: list[Port],
    ports_b: list[Port] | None = None,
    *,
    speed_knots: Decimal,
) -> None:
    ports_b = ports_b if ports_b is not None else ports_a

    rows: list[PortProximity] = []
    for a in ports_a:
        if a.latitude is None or a.longitude is None:
            continue
        for b in ports_b:
            if a.id == b.id:
                continue
            if b.latitude is None or b.longitude is None:
                continue
            dist = haversine_distance_km(
                a.latitude,
                a.longitude,
                b.latitude,
                b.longitude,
            )
            hours = travel_hours_min(dist, speed_knots=speed_knots)
            rows.append(
                PortProximity(
                    from_port_id=a.id,
                    to_port_id=b.id,
                    distance_km=dist.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    travel_hours_min=hours,
                    speed_knots_used=speed_knots,
                )
            )

    if rows:
        PortProximity.objects.bulk_create(rows, batch_size=500)

