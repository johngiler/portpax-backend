from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0039_resync_lta_links_require_position"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="cancellation_notes",
            field=models.TextField(
                blank=True,
                help_text="Free-text comment captured when cancelling (not identity notes).",
            ),
        ),
    ]
