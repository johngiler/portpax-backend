from django.db import migrations, models


def backfill_first_arrival(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    counting = ("co", "cl", "r")
    pairs = (
        Booking.objects.order_by()
        .values_list("vessel_id", "port_id")
        .distinct()
    )
    for vessel_id, port_id in pairs:
        qs = Booking.objects.filter(vessel_id=vessel_id, port_id=port_id)
        qs.filter(first_arrival=True).update(first_arrival=False)
        first = (
            qs.filter(status__in=counting)
            .order_by("call_date", "id")
            .values_list("id", flat=True)
            .first()
        )
        if first:
            Booking.objects.filter(pk=first).update(first_arrival=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0036_lta_shipping_line_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="first_arrival",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "True when this is the earliest CO/CL/R booking for the same "
                    "vessel + port (primer arribo)."
                ),
            ),
        ),
        migrations.RunPython(backfill_first_arrival, noop_reverse),
    ]
