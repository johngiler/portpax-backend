"""Enrich Melilla from authentic pier/mooring layout plans (data only)."""

from decimal import Decimal

from django.db import migrations

FENDER_CYLINDRICAL = "Cylindrical 1.30 m diameter"
FENDER_FOAM = "Foam filled 7′×14′ Advance HC"

SCENARIO_CURRENT_NAME = "3 vessels — current"
SCENARIO_COMING_NAME = "3 vessels — coming soon Cargadero 345"


def _pos_by_suffix(Position, port):
    by_suffix = {}
    for pos in Position.objects.filter(port=port):
        suffix = pos.code.split("-", 1)[-1] if "-" in pos.code else pos.code
        by_suffix[suffix] = pos
    return by_suffix


def _upsert_bollard(PortBollard, port, *, capacity_t, bollard_type, quantity, label, sort_order):
    row = (
        PortBollard.objects.filter(port=port, capacity_t=capacity_t, bollard_type=bollard_type)
        .order_by("id")
        .first()
    )
    if row:
        row.quantity = quantity
        row.label = label
        row.sort_order = sort_order
        row.is_active = True
        row.save(update_fields=["quantity", "label", "sort_order", "is_active", "updated_at"])
        return
    PortBollard.objects.create(
        port=port,
        capacity_t=capacity_t,
        bollard_type=bollard_type,
        quantity=quantity,
        label=label,
        sort_order=sort_order,
        is_active=True,
    )


def _upsert_fender(PortFender, port, *, fender_type, quantity, notes, sort_order):
    row = (
        PortFender.objects.filter(port=port, fender_type=fender_type)
        .order_by("id")
        .first()
    )
    if row:
        row.quantity = quantity
        row.notes = notes
        row.sort_order = sort_order
        row.is_active = True
        row.save(update_fields=["quantity", "notes", "sort_order", "is_active", "updated_at"])
        return
    # Reuse generic "Estándar" row if present (legacy seed).
    legacy = (
        PortFender.objects.filter(port=port, fender_type="Estándar")
        .order_by("id")
        .first()
        if fender_type == FENDER_CYLINDRICAL
        else None
    )
    if legacy:
        legacy.fender_type = fender_type
        legacy.quantity = quantity
        legacy.notes = notes
        legacy.sort_order = sort_order
        legacy.is_active = True
        legacy.save(
            update_fields=["fender_type", "quantity", "notes", "sort_order", "is_active", "updated_at"]
        )
        return
    PortFender.objects.create(
        port=port,
        fender_type=fender_type,
        quantity=quantity,
        notes=notes,
        sort_order=sort_order,
        is_active=True,
    )


def enrich_melilla(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortBollard = apps.get_model("catalogs", "PortBollard")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    MooringScenarioSlot = apps.get_model("catalogs", "MooringScenarioSlot")

    try:
        port = Port.objects.get(code="melilla")
    except Port.DoesNotExist:
        return

    # Physical berth lengths from technical table; LOAs from layout plans.
    berths_spec = [
        (
            "Cargadero",
            "Cargadero",
            Decimal("207.00"),
            Decimal("14.00"),
            Decimal("7.00"),
            (
                "Pier layout (verídico): Cargadero. Min depth zone −7.00 m nearby. "
                "T-head 200 t bollards; cylindrical + foam fenders (in-progress layout)."
            ),
            1,
        ),
        (
            "NE2",
            "Nordeste II",
            Decimal("292.00"),
            Decimal("20.00"),
            Decimal("9.00"),
            "Pier layout (verídico): Nordeste II. Min depth zones −9.00 / −10.00 m.",
            2,
        ),
        (
            "NE3",
            "Nordeste III",
            Decimal("311.00"),
            Decimal("20.00"),
            Decimal("10.00"),
            (
                "Pier layout (verídico): Nordeste III (outer pier). "
                "QRH 200 t + single bitt 200 t; cylindrical fenders 1.30 m. "
                "Future dredging −10.50 m (in-progress layout)."
            ),
            3,
        ),
    ]
    berth_by_code = {}
    for code, name, length_m, width_m, min_draft, notes, sort_order in berths_spec:
        berth, _ = Berth.objects.get_or_create(
            port=port,
            code=code,
            defaults={
                "name": name,
                "length_m": length_m,
                "width_m": width_m,
                "min_draft_m": min_draft,
                "notes": notes,
                "sort_order": sort_order,
                "is_active": True,
            },
        )
        berth.name = name
        berth.length_m = length_m
        berth.width_m = width_m
        berth.min_draft_m = min_draft
        berth.notes = notes
        berth.sort_order = sort_order
        berth.is_active = True
        berth.save()
        berth_by_code[code] = berth

    # Position max LOA = coming-soon physical max; current ops via scenario.
    positions_spec = [
        ("melilla-Cargadero", "Cargadero", Decimal("345.00"), Decimal("7.00"), 1),
        ("melilla-NE2", "NE2", Decimal("278.00"), Decimal("9.00"), 2),
        ("melilla-NE3", "NE3", Decimal("333.00"), Decimal("10.00"), 3),
    ]
    for code, berth_code, max_loa, min_draft, sort_order in positions_spec:
        berth = berth_by_code[berth_code]
        pos, created = Position.objects.get_or_create(
            port=port,
            code=code,
            defaults={
                "berth": berth,
                "position_type": "pier",
                "max_loa_m": max_loa,
                "min_draft_m": min_draft,
                "sort_order": sort_order,
                "is_active": True,
            },
        )
        if not created:
            pos.berth = berth
            pos.position_type = "pier"
            pos.max_loa_m = max_loa
            pos.min_draft_m = min_draft
            pos.sort_order = sort_order
            pos.is_active = True
            pos.save()

    pos = _pos_by_suffix(Position, port)
    cargadero = pos.get("Cargadero")
    ne2 = pos.get("NE2")
    ne3 = pos.get("NE3")

    # In-progress inventory (verídico): QRH 24, T-head 9, single bitt 5+4=9.
    _upsert_bollard(
        PortBollard, port, capacity_t=200, bollard_type="quick_release",
        quantity=24, label="QRH", sort_order=1,
    )
    _upsert_bollard(
        PortBollard, port, capacity_t=200, bollard_type="t_head",
        quantity=9, label="T-head", sort_order=2,
    )
    _upsert_bollard(
        PortBollard, port, capacity_t=200, bollard_type="single_bitt",
        quantity=9, label="Single bitt", sort_order=3,
    )

    # Current: 23+8 cylindrical; in-progress adds 11 foam on Cargadero.
    _upsert_fender(
        PortFender,
        port,
        fender_type=FENDER_CYLINDRICAL,
        quantity=31,
        notes="23 (Nordeste III) + 8 (Cargadero) cylindrical fenders Ø 1.30 m.",
        sort_order=1,
    )
    _upsert_fender(
        PortFender,
        port,
        fender_type=FENDER_FOAM,
        quantity=11,
        notes="11 foam filled 7′×14′ Advance HC on Cargadero (in-progress layout).",
        sort_order=2,
    )

    port.fender_count = 42  # 31 + 11
    port.min_berth_draft_m = Decimal("7.00")
    port.save(update_fields=["fender_count", "min_berth_draft_m", "updated_at"])

    if (
        cargadero
        and ne2
        and ne3
        and not MooringScenario.objects.filter(port=port, name=SCENARIO_CURRENT_NAME).exists()
    ):
        current = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_CURRENT_NAME,
            vessel_count=3,
            is_projection=False,
            notes=(
                "From Port Melilla mooring layout — current three-ship configuration "
                "(Cargadero 227 m + Nordeste II 278 m + Nordeste III 333 m)."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=current, position=cargadero, slot_label="Cargadero",
            max_loa_m=Decimal("227.00"), sort_order=1,
        )
        MooringScenarioSlot.objects.create(
            scenario=current, position=ne2, slot_label="Nordeste II",
            max_loa_m=Decimal("278.00"), sort_order=2,
        )
        MooringScenarioSlot.objects.create(
            scenario=current, position=ne3, slot_label="Nordeste III",
            max_loa_m=Decimal("333.00"), sort_order=3,
        )

    if (
        cargadero
        and ne2
        and ne3
        and not MooringScenario.objects.filter(port=port, name=SCENARIO_COMING_NAME).exists()
    ):
        coming = MooringScenario.objects.create(
            port=port,
            name=SCENARIO_COMING_NAME,
            vessel_count=3,
            is_projection=True,
            notes=(
                "From Port Melilla mooring layout — coming soon three-ship configuration "
                "(Cargadero 345 m + Nordeste II 278 m + Nordeste III 333 m)."
            ),
        )
        MooringScenarioSlot.objects.create(
            scenario=coming, position=cargadero, slot_label="Cargadero",
            max_loa_m=Decimal("345.00"), sort_order=1,
        )
        MooringScenarioSlot.objects.create(
            scenario=coming, position=ne2, slot_label="Nordeste II",
            max_loa_m=Decimal("278.00"), sort_order=2,
        )
        MooringScenarioSlot.objects.create(
            scenario=coming, position=ne3, slot_label="Nordeste III",
            max_loa_m=Decimal("333.00"), sort_order=3,
        )


def revert_melilla(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    PortBollard = apps.get_model("catalogs", "PortBollard")
    PortFender = apps.get_model("catalogs", "PortFender")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")

    try:
        port = Port.objects.get(code="melilla")
    except Port.DoesNotExist:
        return

    MooringScenario.objects.filter(
        port=port,
        name__in=[SCENARIO_CURRENT_NAME, SCENARIO_COMING_NAME],
    ).delete()

    Position.objects.filter(
        port=port,
        code__in=["melilla-Cargadero", "melilla-NE2", "melilla-NE3"],
    ).delete()
    Berth.objects.filter(port=port, code__in=["Cargadero", "NE2", "NE3"]).delete()

    PortBollard.objects.filter(port=port, bollard_type="quick_release").update(quantity=12)
    PortBollard.objects.filter(port=port, bollard_type="single_bitt").update(quantity=5)

    PortFender.objects.filter(port=port).delete()
    PortFender.objects.create(
        port=port,
        fender_type="Estándar",
        quantity=20,
        sort_order=0,
        is_active=True,
    )
    port.fender_count = 20
    port.min_berth_draft_m = Decimal("11.00")
    port.save(update_fields=["fender_count", "min_berth_draft_m", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0029_enrich_la_paz_layouts"),
    ]

    operations = [
        migrations.RunPython(enrich_melilla, revert_melilla),
    ]
