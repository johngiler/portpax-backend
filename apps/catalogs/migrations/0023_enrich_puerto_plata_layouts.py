"""Enrich Puerto Plata (Taino Bay) from authentic pier/mooring layout plans."""

from decimal import Decimal

from django.db import migrations

SCENARIO_3_NAME = "3 vessels — current layout"

BERTH_NOTES = (
    "Pier layout (verídico): total 621.90 m; outer tip section 327.25 m. "
    "Min depths by zone: W −11.00 m, outer −11.50 m, E outer −12.00 m, E inner −11.00 m."
)

FENDER_TYPE = "Foam filled 7′×14′ Advance HC"
FENDER_NOTES = "24 foam filled fenders 7′×14′ Advance High Capacity (pier layout)."


def enrich_puerto_plata(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    MooringScenarioSlot = apps.get_model("catalogs", "MooringScenarioSlot")

    try:
        port = Port.objects.get(code="puerto_plata")
    except Port.DoesNotExist:
        return

    berth = Berth.objects.filter(port=port, code="M1").first()
    if berth:
        berth.length_m = Decimal("621.90")
        berth.notes = BERTH_NOTES
        berth.save(update_fields=["length_m", "notes", "updated_at"])

    pos_by_suffix = {}
    for pos in Position.objects.filter(port=port):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        pos_by_suffix[suffix] = pos

    w3 = pos_by_suffix.get("W3")
    if w3:
        w3.max_loa_m = Decimal("333.00")
        w3.save(update_fields=["max_loa_m", "updated_at"])

    e1e2 = pos_by_suffix.get("E1+E2")
    if e1e2:
        e1e2.max_loa_m = Decimal("365.00")
        e1e2.save(update_fields=["max_loa_m", "updated_at"])

    fender = PortFender.objects.filter(port=port, is_active=True).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = FENDER_TYPE
        fender.notes = FENDER_NOTES
        fender.save(update_fields=["fender_type", "notes", "updated_at"])

    e1 = pos_by_suffix.get("E1")
    e2 = pos_by_suffix.get("E2")
    if not MooringScenario.objects.filter(port=port, name=SCENARIO_3_NAME).exists() and e1 and e2 and w3:
        scenario = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_3_NAME,
            vessel_count=3,
            is_projection=False,
            notes="From Taino Bay mooring layout — three ship configuration.",
        )
        MooringScenarioSlot.objects.create(
            scenario=scenario,
            position=e1,
            slot_label="E1",
            max_loa_m=Decimal("305.00"),
            sort_order=1,
        )
        MooringScenarioSlot.objects.create(
            scenario=scenario,
            position=e2,
            slot_label="E2",
            max_loa_m=Decimal("334.00"),
            sort_order=2,
        )
        MooringScenarioSlot.objects.create(
            scenario=scenario,
            position=w3,
            slot_label="W3",
            max_loa_m=Decimal("333.00"),
            sort_order=3,
        )

def revert_puerto_plata(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")

    try:
        port = Port.objects.get(code="puerto_plata")
    except Port.DoesNotExist:
        return

    berth = Berth.objects.filter(port=port, code="M1").first()
    if berth:
        berth.length_m = Decimal("622.25")
        berth.notes = ""
        berth.save(update_fields=["length_m", "notes", "updated_at"])

    positions = Position.objects.filter(port=port)
    for pos in positions:
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        if suffix == "W3":
            pos.max_loa_m = Decimal("327.25")
            pos.save(update_fields=["max_loa_m", "updated_at"])
        elif suffix == "E1+E2":
            pos.max_loa_m = Decimal("639.00")
            pos.save(update_fields=["max_loa_m", "updated_at"])

    fender = PortFender.objects.filter(port=port).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = "Estándar"
        fender.notes = ""
        fender.save(update_fields=["fender_type", "notes", "updated_at"])

    MooringScenario.objects.filter(port=port, name=SCENARIO_3_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0022_position_max_beam_m_position_min_eta_and_more"),
    ]

    operations = [
        migrations.RunPython(enrich_puerto_plata, revert_puerto_plata),
    ]
