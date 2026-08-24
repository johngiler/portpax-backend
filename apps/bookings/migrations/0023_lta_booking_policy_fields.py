# Generated manually for LTA blockcito policy fields.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bookings", "0022_refresh_multi_port_conflict_messages"),
    ]

    operations = [
        migrations.AddField(
            model_name="longtermagreement",
            name="booking_policy",
            field=models.CharField(
                choices=[
                    ("standard", "Standard"),
                    ("rci_staggered", "RCI staggered"),
                ],
                default="standard",
                help_text="Standard = any LTA season in depth; RCI = staggered Summer/Winter.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="longtermagreement",
            name="lta_depth_blocks",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text="How many 6-month LTA blocks (after open booking) this agreement covers.",
            ),
        ),
        migrations.AddField(
            model_name="longtermagreement",
            name="reserve_foreign_slots",
            field=models.BooleanField(
                default=True,
                help_text="When true, blocks other lines on reserved weekday+position in LTA zone.",
            ),
        ),
    ]
