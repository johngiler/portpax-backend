"""Enrich Roatán from authentic pier/mooring layout plans (data only)."""

from decimal import Decimal

from django.db import migrations

SCENARIO_CURRENT_NAME = "2 pier vessels — current"
SCENARIO_PROJECTED_NAME = "2 pier vessels — projected 365+365"

P1_NOTES = (
    "Pier layout (verídico): main pier length 366.00 m. "
    "Min depth at berth line −12.00 m."
)
P2_NOTES = (
    "Pier layout (verídico): secondary pier length 215.00 m. "
    "Adjacent deep-water zone marked −30.00 m on layout (not berth draft)."
)

FENDER_TYPE = "Foam filled 7′×14′ Advance HC"
FENDER_NOTES = "16 foam filled fenders 7′×14′ Advance High Capacity (pier layout)."


def _pos_by_suffix(Position, port):
    by_suffix = {}
    for pos in Position.objects.filter(port=port):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        by_suffix[suffix] = pos
    return by_suffix


def enrich_roatan(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    MooringScenarioSlot = apps.get_model("catalogs", "MooringScenarioSlot")

    try:
        port = Port.objects.get(code="roatan")
    except Port.DoesNotExist:
        return

    berth_p1 = Berth.objects.filter(port=port, code="P1").first()
    if berth_p1:
        berth_p1.length_m = Decimal("366.00")
        berth_p1.min_draft_m = Decimal("12.00")
        berth_p1.notes = P1_NOTES
        berth_p1.save(update_fields=["length_m", "min_draft_m", "notes", "updated_at"])

    berth_p2 = Berth.objects.filter(port=port, code="P2").first()
    if berth_p2:
        berth_p2.length_m = Decimal("215.00")
        berth_p2.min_draft_m = Decimal("12.00")
        berth_p2.notes = P2_NOTES
        berth_p2.save(update_fields=["length_m", "min_draft_m", "notes", "updated_at"])

    pos = _pos_by_suffix(Position, port)
    p1 = pos.get("P1")
    p2 = pos.get("P2")

    # P1/P2 physical max LOA from layouts (both configs allow up to 365 on P1;
    # projected layout allows 365 on P2). Keep position max at 365.
    if p1 and p1.max_loa_m != Decimal("365.00"):
        p1.max_loa_m = Decimal("365.00")
        p1.min_draft_m = Decimal("12.00")
        p1.save(update_fields=["max_loa_m", "min_draft_m", "updated_at"])
    if p2 and p2.max_loa_m != Decimal("365.00"):
        p2.max_loa_m = Decimal("365.00")
        p2.min_draft_m = Decimal("12.00")
        p2.save(update_fields=["max_loa_m", "min_draft_m", "updated_at"])

    fender = PortFender.objects.filter(port=port, is_active=True).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = FENDER_TYPE
        fender.notes = FENDER_NOTES
        fender.save(update_fields=["fender_type", "notes", "updated_at"])

    # Ensure current scenario slots match layout (P1 365 + P2 333, gap 48 m).
    current = MooringScenario.objects.filter(port=port, name=SCENARIO_CURRENT_NAME).first()
    if current and p1 and p2:
        current.vessel_count = 2
        current.is_projection = False
        current.notes = (
            "From Port Roatán mooring layout — two ship configuration "
            "(P1 365 m + P2 333 m; gap 48.00 m)."
        )
        current.save(update_fields=["vessel_count", "is_projection", "notes", "updated_at"])
        slots = {s.slot_label: s for s in current.slots.all()}
        if "P1" in slots:
            slots["P1"].position = p1
            slots["P1"].max_loa_m = Decimal("365.00")
            slots["P1"].sort_order = 1
            slots["P1"].save(update_fields=["position", "max_loa_m", "sort_order"])
        else:
            MooringScenarioSlot.objects.create(
                scenario=current,
                position=p1,
                slot_label="P1",
                max_loa_m=Decimal("365.00"),
                sort_order=1,
            )
        if "P2" in slots:
            slots["P2"].position = p2
            slots["P2"].max_loa_m = Decimal("333.00")
            slots["P2"].sort_order = 2
            slots["P2"].save(update_fields=["position", "max_loa_m", "sort_order"])
        else:
            MooringScenarioSlot.objects.create(
                scenario=current,
                position=p2,
                slot_label="P2",
                max_loa_m=Decimal("333.00"),
                sort_order=2,
            )

    if (
        not MooringScenario.objects.filter(port=port, name=SCENARIO_PROJECTED_NAME).exists()
        and p1
        and p2
    ):
        projected = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_PROJECTED_NAME,
            vessel_count=2,
            is_projection=True,
            notes=(
                "From Port Roatán mooring layout — two ship configuration "
                "(P1 365 m + P2 365 m; gap 45.00 m)."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=projected,
            position=p1,
            slot_label="P1",
            max_loa_m=Decimal("365.00"),
            sort_order=1,
        )
        MooringScenarioSlot.objects.create(
            scenario=projected,
            position=p2,
            slot_label="P2",
            max_loa_m=Decimal("365.00"),
            sort_order=2,
        )


def revert_roatan(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")

    try:
        port = Port.objects.get(code="roatan")
    except Port.DoesNotExist:
        return

    berth_p1 = Berth.objects.filter(port=port, code="P1").first()
    if berth_p1:
        berth_p1.length_m = Decimal("180.00")
        berth_p1.notes = ""
        berth_p1.save(update_fields=["length_m", "notes", "updated_at"])

    berth_p2 = Berth.objects.filter(port=port, code="P2").first()
    if berth_p2:
        berth_p2.length_m = Decimal("250.00")
        berth_p2.notes = ""
        berth_p2.save(update_fields=["length_m", "notes", "updated_at"])

    fender = PortFender.objects.filter(port=port).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = "Estándar"
        fender.notes = ""
        fender.save(update_fields=["fender_type", "notes", "updated_at"])

    MooringScenario.objects.filter(port=port, name=SCENARIO_PROJECTED_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0023_enrich_puerto_plata_layouts"),
    ]

    operations = [
        migrations.RunPython(enrich_roatan, revert_roatan),
    ]
