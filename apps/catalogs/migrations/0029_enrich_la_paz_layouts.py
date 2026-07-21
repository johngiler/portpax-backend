"""Enrich La Paz from authentic pier/mooring layout plans (data only)."""

from decimal import Decimal

from django.db import migrations

BERTH_CODE = "main"
BERTH_NOTES = (
    "Pier layout (verídico): berthing length 200.00 m. "
    "Min depth −11.50 m. Bollards: 2×200 t + 2×150 t + 13×100 t + 2×50 t. "
    "Pier extension proposal enables LOA 347 m (one-ship)."
)

FENDER_TYPE = "Foam filled 7′×14′ Advance HC"
FENDER_NOTES = "6 foam filled fenders 7′×14′ Advance High Capacity (pier layout)."

SCENARIO_CURRENT_NAME = "1 vessel — current LOA 323"
SCENARIO_EXTENSION_NAME = "1 vessel — pier extension proposal LOA 347"


def _pos_by_suffix(Position, port):
    by_suffix = {}
    for pos in Position.objects.filter(port=port):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        by_suffix[suffix] = pos
    return by_suffix


def enrich_la_paz(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    MooringScenarioSlot = apps.get_model("catalogs", "MooringScenarioSlot")

    try:
        port = Port.objects.get(code="la_paz")
    except Port.DoesNotExist:
        return

    berth = Berth.objects.filter(port=port, code=BERTH_CODE).first()
    if berth:
        berth.length_m = Decimal("200.00")
        berth.min_draft_m = Decimal("11.50")
        berth.notes = BERTH_NOTES
        berth.save(update_fields=["length_m", "min_draft_m", "notes", "updated_at"])

    if port.min_berth_draft_m != Decimal("11.50"):
        port.min_berth_draft_m = Decimal("11.50")
        port.save(update_fields=["min_berth_draft_m", "updated_at"])

    # Single pier position (one-ship configs only). Keep existing code la_paz-P1.
    pos = _pos_by_suffix(Position, port)
    p1 = pos.get("P1")
    if p1:
        # Physical max from extension proposal; current ops constrained via scenario.
        p1.max_loa_m = Decimal("347.00")
        p1.min_draft_m = Decimal("11.50")
        p1.position_type = "pier"
        if berth:
            p1.berth = berth
        p1.save(update_fields=["max_loa_m", "min_draft_m", "position_type", "berth", "updated_at"])
    elif berth:
        p1 = Position.objects.create(
            port=port,
            berth=berth,
            code="la_paz-P1",
            position_type="pier",
            max_loa_m=Decimal("347.00"),
            min_draft_m=Decimal("11.50"),
            sort_order=1,
            is_active=True,
        )

    fender = PortFender.objects.filter(port=port, is_active=True).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = FENDER_TYPE
        fender.notes = FENDER_NOTES
        fender.quantity = 6
        fender.save(update_fields=["fender_type", "notes", "quantity", "updated_at"])

    if port.fender_count != 6:
        port.fender_count = 6
        port.save(update_fields=["fender_count", "updated_at"])

    if p1 and not MooringScenario.objects.filter(port=port, name=SCENARIO_CURRENT_NAME).exists():
        current = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_CURRENT_NAME,
            vessel_count=1,
            is_projection=False,
            notes=(
                "From Port La Paz mooring layout — current one-ship configuration "
                "(POSITION LOA 323 m)."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=current,
            position=p1,
            slot_label="P1",
            max_loa_m=Decimal("323.00"),
            sort_order=1,
        )

    if p1 and not MooringScenario.objects.filter(port=port, name=SCENARIO_EXTENSION_NAME).exists():
        extension = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_EXTENSION_NAME,
            vessel_count=1,
            is_projection=True,
            notes=(
                "From Port La Paz mooring layout — pier extension proposal "
                "(one-ship POSITION LOA 347 m)."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=extension,
            position=p1,
            slot_label="P1",
            max_loa_m=Decimal("347.00"),
            sort_order=1,
        )


def revert_la_paz(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")

    try:
        port = Port.objects.get(code="la_paz")
    except Port.DoesNotExist:
        return

    MooringScenario.objects.filter(
        port=port,
        name__in=[SCENARIO_CURRENT_NAME, SCENARIO_EXTENSION_NAME],
    ).delete()

    berth = Berth.objects.filter(port=port, code=BERTH_CODE).first()
    if berth:
        berth.min_draft_m = Decimal("11.00")
        berth.notes = ""
        berth.save(update_fields=["min_draft_m", "notes", "updated_at"])

    port.min_berth_draft_m = Decimal("11.00")
    port.save(update_fields=["min_berth_draft_m", "updated_at"])

    p1 = Position.objects.filter(port=port, code="la_paz-P1").first()
    if p1:
        p1.max_loa_m = Decimal("200.00")
        p1.min_draft_m = Decimal("12.00")
        p1.save(update_fields=["max_loa_m", "min_draft_m", "updated_at"])

    fender = PortFender.objects.filter(port=port).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = "Estándar"
        fender.notes = ""
        fender.save(update_fields=["fender_type", "notes", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0028_enrich_cabo_rojo_layouts"),
    ]

    operations = [
        migrations.RunPython(enrich_la_paz, revert_la_paz),
    ]
