"""Enrich Cabo Rojo from authentic pier/mooring layout plans (data only)."""

from datetime import date
from decimal import Decimal

from django.db import migrations

BERTH_CODE = "M1"
BERTH_NOTES = (
    "Pier layout (verídico): berthing length 600.00 m; 27×200 t bollards. "
    "Min depth zones on layout: channel −11.00 / −11.50 m, near shore −13.00 m, "
    "approach −17.00 m, deep basin −50.00 m."
)

FENDER_TYPE = "Foam filled 7′×14′ Advance HC"
FENDER_NOTES = "24 foam filled fenders 7′×14′ Advance High Capacity (pier layout)."

SCENARIO_CURRENT_NAME = "2 vessels — current N1 365 + S2 333"
SCENARIO_PROJECTED_NAME = "2 vessels — Dec 2028 projected 365+365"


def _pos_by_suffix(Position, port):
    by_suffix = {}
    for pos in Position.objects.filter(port=port):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        by_suffix[suffix] = pos
    return by_suffix


def enrich_cabo_rojo(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortBollard = apps.get_model("catalogs", "PortBollard")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    MooringScenarioSlot = apps.get_model("catalogs", "MooringScenarioSlot")

    try:
        port = Port.objects.get(code="cabo_rojo")
    except Port.DoesNotExist:
        return

    berth, _ = Berth.objects.get_or_create(
        port=port,
        code=BERTH_CODE,
        defaults={
            "name": "Muelle Principal",
            "length_m": Decimal("600.00"),
            "width_m": Decimal("16.00"),
            "min_draft_m": Decimal("12.00"),
            "notes": BERTH_NOTES,
            "sort_order": 1,
            "is_active": True,
        },
    )
    berth.name = berth.name or "Muelle Principal"
    berth.length_m = Decimal("600.00")
    berth.min_draft_m = Decimal("12.00")
    berth.notes = BERTH_NOTES
    berth.sort_order = 1
    berth.is_active = True
    berth.save()

    # Layout is pier-only: N1 (north) + S2 (south). No anchorages.
    for code, max_loa, sort_order in (
        ("cabo_rojo-N1", Decimal("365.00"), 1),
        ("cabo_rojo-S2", Decimal("365.00"), 2),
    ):
        pos, created = Position.objects.get_or_create(
            port=port,
            code=code,
            defaults={
                "berth": berth,
                "position_type": "pier",
                "max_loa_m": max_loa,
                "min_draft_m": Decimal("12.00"),
                "sort_order": sort_order,
                "is_active": True,
            },
        )
        if not created:
            pos.berth = berth
            pos.position_type = "pier"
            pos.max_loa_m = max_loa
            pos.min_draft_m = Decimal("12.00")
            pos.sort_order = sort_order
            pos.is_active = True
            pos.save()

    pos = _pos_by_suffix(Position, port)
    n1 = pos.get("N1")
    s2 = pos.get("S2")

    bollard = (
        PortBollard.objects.filter(port=port, capacity_t=200, is_active=True)
        .order_by("sort_order", "id")
        .first()
    )
    if bollard:
        bollard.quantity = 27
        bollard.save(update_fields=["quantity", "updated_at"])

    fender = PortFender.objects.filter(port=port, is_active=True).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = FENDER_TYPE
        fender.notes = FENDER_NOTES
        fender.quantity = 24
        fender.save(update_fields=["fender_type", "notes", "quantity", "updated_at"])

    if port.fender_count != 24:
        port.fender_count = 24
        port.save(update_fields=["fender_count", "updated_at"])

    if n1 and s2 and not MooringScenario.objects.filter(port=port, name=SCENARIO_CURRENT_NAME).exists():
        current = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_CURRENT_NAME,
            vessel_count=2,
            is_projection=False,
            notes=(
                "From Port Cabo Rojo mooring layout — two-ship configuration "
                "(N1 365 m + S2 333 m)."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=current,
            position=n1,
            slot_label="N1",
            max_loa_m=Decimal("365.00"),
            sort_order=1,
        )
        MooringScenarioSlot.objects.create(
            scenario=current,
            position=s2,
            slot_label="S2",
            max_loa_m=Decimal("333.00"),
            sort_order=2,
        )

    if n1 and s2 and not MooringScenario.objects.filter(port=port, name=SCENARIO_PROJECTED_NAME).exists():
        projected = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_PROJECTED_NAME,
            vessel_count=2,
            is_projection=True,
            effective_from=date(2028, 12, 1),
            notes=(
                "From Port Cabo Rojo mooring layout — December 2028 projected "
                "two-ship configuration (N1 365 m + S2 365 m)."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=projected,
            position=n1,
            slot_label="N1",
            max_loa_m=Decimal("365.00"),
            sort_order=1,
        )
        MooringScenarioSlot.objects.create(
            scenario=projected,
            position=s2,
            slot_label="S2",
            max_loa_m=Decimal("365.00"),
            sort_order=2,
        )


def revert_cabo_rojo(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortBollard = apps.get_model("catalogs", "PortBollard")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")

    try:
        port = Port.objects.get(code="cabo_rojo")
    except Port.DoesNotExist:
        return

    MooringScenario.objects.filter(
        port=port,
        name__in=[SCENARIO_CURRENT_NAME, SCENARIO_PROJECTED_NAME],
    ).delete()

    Position.objects.filter(
        port=port,
        code__in=["cabo_rojo-N1", "cabo_rojo-S2"],
    ).delete()

    berth = Berth.objects.filter(port=port, code=BERTH_CODE).first()
    if berth:
        berth.length_m = Decimal("401.00")
        berth.notes = ""
        berth.save(update_fields=["length_m", "notes", "updated_at"])

    bollard = (
        PortBollard.objects.filter(port=port, capacity_t=200)
        .order_by("sort_order", "id")
        .first()
    )
    if bollard:
        bollard.quantity = 24
        bollard.save(update_fields=["quantity", "updated_at"])

    fender = PortFender.objects.filter(port=port).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = "Estándar"
        fender.notes = ""
        fender.save(update_fields=["fender_type", "notes", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0027_samana_remove_anchorages"),
    ]

    operations = [
        migrations.RunPython(enrich_cabo_rojo, revert_cabo_rojo),
    ]
