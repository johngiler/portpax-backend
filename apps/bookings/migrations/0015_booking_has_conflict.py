from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0014_seed_msc_lta_agreements"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="has_conflict",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="True when operational conflicts (non-blocking) are present.",
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="conflict_snapshot",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Normalized conflict items (code, severity, message, detail).",
            ),
        ),
    ]
