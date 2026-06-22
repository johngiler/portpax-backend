import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0009_seed_port_bollards"),
    ]

    operations = [
        migrations.CreateModel(
            name="BerthImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="berths/gallery/")),
                ("caption", models.CharField(blank=True, max_length=255)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "is_cover",
                    models.BooleanField(
                        default=False,
                        help_text="Cover image shown on berth cards.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "berth",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="catalogs.berth",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
    ]
