"""Port fender line inventory (mirrors port bollard pattern)."""

from django.db import migrations, models
import django.db.models.deletion


def seed_fenders_from_port_totals(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    PortFender = apps.get_model("catalogs", "PortFender")

    for port in Port.objects.all():
        if port.fender_count is None or port.fender_count < 1:
            continue
        PortFender.objects.create(
            port=port,
            fender_type="Estándar",
            quantity=port.fender_count,
            notes="",
            sort_order=0,
            is_active=True,
        )


def unseed_fenders(apps, schema_editor):
    PortFender = apps.get_model("catalogs", "PortFender")
    PortFender.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalogs", "0017_prefix_position_codes"),
    ]

    operations = [
        migrations.CreateModel(
            name="PortFender",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fender_type", models.CharField(max_length=64)),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "port",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fenders",
                        to="catalogs.port",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "fender_type"],
            },
        ),
        migrations.RunPython(seed_fenders_from_port_totals, unseed_fenders),
    ]
