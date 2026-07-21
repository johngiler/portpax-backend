"""Enrich Samaná from authentic pier/mooring layout plans (data only)."""

from datetime import date
from decimal import Decimal

from django.db import migrations

BERTH_CODE = "main"
BERTH_NOTES = (
    "Pier layout (verídico): berthing length 396.60 m, width ~20 m; "
    "outer mooring dolphins beyond pier tip. "
    "Min depth zones −10.00 m / −12.00 m; future dredging −11.00 m (Nov 2027 layout)."
)

FENDER_TYPE = "Foam filled 7′×14′ Advance HC"
FENDER_NOTES = "18 foam filled fenders 7′×14′ Advance High Capacity (pier layout)."

# Mooring layout: COMING JANUARY 2027 — S1 365 + N2 333
SCENARIO_PHASE1_NAME = "2 vessels — Jan 2027"
# Pier layout: COMING NOVEMBER 2027 — projected 365+365 + future dredging −11 m
SCENARIO_PHASE2_NAME = "2 vessels — Nov 2027 projected 365+365"


def _pos_by_suffix(Position, port):
    by_suffix = {}
    for pos in Position.objects.filter(port=port):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        by_suffix[suffix] = pos
    return by_suffix


def enrich_samana(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    MooringScenarioSlot = apps.get_model("catalogs", "MooringScenarioSlot")

    try:
        port = Port.objects.get(code="samana")
    except Port.DoesNotExist:
        return

    berth, _ = Berth.objects.get_or_create(
        port=port,
        code=BERTH_CODE,
        defaults={
            "name": "Main pier",
            "length_m": Decimal("396.60"),
            "width_m": Decimal("20.00"),
            "min_draft_m": Decimal("12.00"),
            "notes": BERTH_NOTES,
            "sort_order": 1,
            "is_active": True,
        },
    )
    berth.name = "Main pier"
    berth.length_m = Decimal("396.60")
    berth.width_m = Decimal("20.00")
    berth.min_draft_m = Decimal("12.00")
    berth.notes = BERTH_NOTES
    berth.sort_order = 1
    berth.is_active = True
    berth.save()

    # Prefixed codes (migration 0017 convention). Layout is pier-only (no anchorages).
    positions_spec = [
        ("samana-S1", "pier", berth, Decimal("365.00"), Decimal("12.00"), 1),
        ("samana-N2", "pier", berth, Decimal("365.00"), Decimal("12.00"), 2),
    ]
    for code, position_type, berth_ref, max_loa, min_draft, sort_order in positions_spec:
        pos, created = Position.objects.get_or_create(
            port=port,
            code=code,
            defaults={
                "berth": berth_ref,
                "position_type": position_type,
                "max_loa_m": max_loa,
                "min_draft_m": min_draft,
                "sort_order": sort_order,
                "is_active": True,
            },
        )
        if not created:
            pos.berth = berth_ref
            pos.position_type = position_type
            pos.max_loa_m = max_loa
            pos.min_draft_m = min_draft
            pos.sort_order = sort_order
            pos.is_active = True
            pos.save()

    pos = _pos_by_suffix(Position, port)
    s1 = pos.get("S1")
    n2 = pos.get("N2")

    fender = PortFender.objects.filter(port=port, is_active=True).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = FENDER_TYPE
        fender.notes = FENDER_NOTES
        fender.save(update_fields=["fender_type", "notes", "updated_at"])

    if s1 and n2 and not MooringScenario.objects.filter(port=port, name=SCENARIO_PHASE1_NAME).exists():
        phase1 = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_PHASE1_NAME,
            vessel_count=2,
            is_projection=False,
            effective_from=date(2027, 1, 1),
            notes=(
                "From Port Samaná mooring layout — January 2027 two-ship configuration "
                "(S1 365 m + N2 333 m)."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=phase1,
            position=s1,
            slot_label="S1",
            max_loa_m=Decimal("365.00"),
            sort_order=1,
        )
        MooringScenarioSlot.objects.create(
            scenario=phase1,
            position=n2,
            slot_label="N2",
            max_loa_m=Decimal("333.00"),
            sort_order=2,
        )

    if s1 and n2 and not MooringScenario.objects.filter(port=port, name=SCENARIO_PHASE2_NAME).exists():
        phase2 = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_PHASE2_NAME,
            vessel_count=2,
            is_projection=True,
            effective_from=date(2027, 11, 1),
            notes=(
                "From Samaná pier layout — Nov 2027 projected two-ship configuration "
                "(S1 365 m + N2 365 m); future dredging to −11.00 m."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=phase2,
            position=s1,
            slot_label="S1",
            max_loa_m=Decimal("365.00"),
            sort_order=1,
        )
        MooringScenarioSlot.objects.create(
            scenario=phase2,
            position=n2,
            slot_label="N2",
            max_loa_m=Decimal("365.00"),
            sort_order=2,
        )


def revert_samana(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")

    try:
        port = Port.objects.get(code="samana")
    except Port.DoesNotExist:
        return

    MooringScenario.objects.filter(
        port=port,
        name__in=[SCENARIO_PHASE1_NAME, SCENARIO_PHASE2_NAME],
    ).delete()

    Position.objects.filter(
        port=port,
        code__in=["samana-S1", "samana-N2"],
    ).delete()
    Berth.objects.filter(port=port, code=BERTH_CODE).delete()

    fender = PortFender.objects.filter(port=port).order_by("sort_order", "id").first()
    if fender:
        fender.fender_type = "Estándar"
        fender.notes = ""
        fender.save(update_fields=["fender_type", "notes", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0024_enrich_roatan_layouts"),
    ]

    operations = [
        migrations.RunPython(enrich_samana, revert_samana),
    ]
