from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models
import django.db.models.deletion


DEFAULT_SPEED_KNOTS = Decimal("10.00")
SPEED_KM_H = DEFAULT_SPEED_KNOTS * Decimal("1.852")
EARTH_RADIUS_KM = Decimal("6371.0088")
Q_2 = Decimal("0.01")


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _haversine_km(lat1: Decimal, lon1: Decimal, lat2: Decimal, lon2: Decimal) -> Decimal:
    import math

    lat1_f = float(lat1)
    lon1_f = float(lon1)
    lat2_f = float(lat2)
    lon2_f = float(lon2)

    dlat = math.radians(lat2_f - lat1_f)
    dlon = math.radians(lon2_f - lon1_f)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1_f))
        * math.cos(math.radians(lat2_f))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    dist_km = float(EARTH_RADIUS_KM) * c
    return Decimal(str(dist_km))


def _travel_hours_min(distance_km: Decimal) -> Decimal:
    if SPEED_KM_H <= 0:
        return Decimal("999999")
    hours = distance_km / SPEED_KM_H
    return hours.quantize(Q_2, rounding=ROUND_HALF_UP)


def seed_port_proximity(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    PortProximity = apps.get_model("catalogs", "PortProximity")

    ports = list(
        Port.objects.filter(
            is_active=True,
            latitude__isnull=False,
            longitude__isnull=False,
        )
    )
    PortProximity.objects.all().delete()

    rows = []
    for a in ports:
        for b in ports:
            if a.id == b.id:
                continue
            if b.latitude is None or b.longitude is None:
                continue
            dist = _haversine_km(a.latitude, a.longitude, b.latitude, b.longitude).quantize(
                Q_2, rounding=ROUND_HALF_UP
            )
            hours = _travel_hours_min(dist)
            rows.append(
                PortProximity(
                    from_port_id=a.id,
                    to_port_id=b.id,
                    distance_km=dist,
                    travel_hours_min=hours,
                    speed_knots_used=DEFAULT_SPEED_KNOTS,
                )
            )

    if rows:
        PortProximity.objects.bulk_create(rows, batch_size=500)


def unseed_port_proximity(apps, schema_editor):
    PortProximity = apps.get_model("catalogs", "PortProximity")
    PortProximity.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0038_vessel_ship_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="PortProximity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "distance_km",
                    models.DecimalField(decimal_places=2, max_digits=10),
                ),
                (
                    "travel_hours_min",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        help_text="Minimum travel time between ports using the configured default speed.",
                    ),
                ),
                (
                    "speed_knots_used",
                    models.DecimalField(
                        decimal_places=2,
                        default=DEFAULT_SPEED_KNOTS,
                        max_digits=6,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "from_port",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proximity_from",
                        to="catalogs.port",
                    ),
                ),
                (
                    "to_port",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proximity_to",
                        to="catalogs.port",
                    ),
                ),
            ],
            options={
                "ordering": ["from_port_id", "to_port_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="portproximity",
            constraint=models.UniqueConstraint(
                fields=("from_port", "to_port"),
                name="catalogs_portproximity_from_to_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="portproximity",
            constraint=models.CheckConstraint(
                condition=~models.Q(from_port=models.F("to_port")),
                name="catalogs_portproximity_from_not_equal_to",
            ),
        ),
        migrations.RunPython(seed_port_proximity, unseed_port_proximity),
    ]

