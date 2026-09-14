# Generated manually — LTA ownership by shipping-line group.

from django.db import migrations, models
import django.db.models.deletion


def backfill_shipping_line_group(apps, schema_editor):
    LongTermAgreement = apps.get_model("bookings", "LongTermAgreement")
    for agreement in LongTermAgreement.objects.select_related("shipping_line").iterator():
        line = agreement.shipping_line
        if line is None or line.group_id is None:
            raise RuntimeError(
                f"LTA {agreement.pk} ({agreement.code}) has no shipping_line.group; "
                "fix catalog before migrating."
            )
        agreement.shipping_line_group_id = line.group_id
        agreement.save(update_fields=["shipping_line_group_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0041_alter_positionloarecalcrule_red_from_m_and_more"),
        ("bookings", "0035_delete_empty_lta_agreement_run_batches"),
    ]

    operations = [
        migrations.AddField(
            model_name="longtermagreement",
            name="shipping_line_group",
            field=models.ForeignKey(
                help_text="Corporate group that owns this LTA (claim/match scope).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="long_term_agreements",
                to="catalogs.shippinglinegroup",
            ),
        ),
        migrations.RunPython(backfill_shipping_line_group, noop_reverse),
        migrations.AlterField(
            model_name="longtermagreement",
            name="shipping_line_group",
            field=models.ForeignKey(
                help_text="Corporate group that owns this LTA (claim/match scope).",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="long_term_agreements",
                to="catalogs.shippinglinegroup",
            ),
        ),
        migrations.AlterField(
            model_name="longtermagreement",
            name="all_vessels",
            field=models.BooleanField(
                default=True,
                help_text="If true, all vessels of the shipping-line group are covered.",
            ),
        ),
        migrations.AlterField(
            model_name="longtermagreement",
            name="shipping_line",
            field=models.ForeignKey(
                help_text="Titular brand for codes / generated LTA booking stamp.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="long_term_agreements",
                to="catalogs.shippingline",
            ),
        ),
        migrations.AlterModelOptions(
            name="longtermagreement",
            options={"ordering": ["port", "shipping_line_group", "code"]},
        ),
    ]
