"""Seed port catalog from docs/muelles_especificaciones.html (structure only, no bollards)."""

from decimal import Decimal

from django.db import migrations


def seed_catalog(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Berth = apps.get_model("catalogs", "Berth")
    Position = apps.get_model("catalogs", "Position")
    MooringScenario = apps.get_model("catalogs", "MooringScenario")
    MooringScenarioSlot = apps.get_model("catalogs", "MooringScenarioSlot")

    ports = [
        {
            "code": "la_paz",
            "name": "La Paz",
            "commercial_name": "",
            "country": "Mexico",
            "region": "Baja California Sur",
            "latitude": Decimal("24.277500"),
            "longitude": Decimal("-110.327500"),
            "status": "operational",
            "min_berth_draft_m": Decimal("11.00"),
            "anchorage_slot_count": 0,
            "largest_vessel_recorded": "Carnival Panorama",
            "largest_vessel_loa_m": Decimal("323.00"),
        },
        {
            "code": "puerto_plata",
            "name": "Puerto Plata",
            "commercial_name": "Taino Bay",
            "country": "Dominican Republic",
            "region": "Puerto Plata",
            "latitude": Decimal("19.823056"),
            "longitude": Decimal("-70.743889"),
            "status": "operational",
            "min_berth_draft_m": Decimal("11.00"),
            "anchorage_slot_count": 0,
            "largest_vessel_recorded": "Wonder of the Seas",
            "largest_vessel_loa_m": Decimal("362.00"),
        },
        {
            "code": "cabo_rojo",
            "name": "Cabo Rojo",
            "commercial_name": "",
            "country": "Dominican Republic",
            "region": "Pedernales",
            "latitude": Decimal("17.970000"),
            "longitude": Decimal("-71.666111"),
            "status": "operational",
            "min_berth_draft_m": Decimal("12.00"),
            "anchorage_slot_count": 0,
            "largest_vessel_recorded": "Oasis of the Seas",
            "largest_vessel_loa_m": Decimal("362.00"),
        },
        {
            "code": "roatan",
            "name": "Roatán",
            "commercial_name": "",
            "country": "Honduras",
            "region": "Bay Islands",
            "latitude": Decimal("16.337222"),
            "longitude": Decimal("-86.519167"),
            "status": "operational",
            "min_berth_draft_m": Decimal("12.00"),
            "anchorage_slot_count": 2,
            "largest_vessel_recorded": "Icon of the Seas",
            "largest_vessel_loa_m": Decimal("365.00"),
        },
        {
            "code": "samana",
            "name": "Samaná",
            "commercial_name": "",
            "country": "Dominican Republic",
            "region": "Samaná",
            "latitude": Decimal("19.326944"),
            "longitude": Decimal("-69.455000"),
            "status": "in_development",
            "min_berth_draft_m": Decimal("12.00"),
            "anchorage_slot_count": 2,
            "largest_vessel_recorded": "",
            "largest_vessel_loa_m": None,
        },
        {
            "code": "melilla",
            "name": "Melilla",
            "commercial_name": "",
            "country": "Spain",
            "region": "Melilla",
            "latitude": Decimal("35.290556"),
            "longitude": Decimal("-2.926111"),
            "status": "planned_extension",
            "min_berth_draft_m": Decimal("11.00"),
            "anchorage_slot_count": 0,
            "largest_vessel_recorded": "Costa Fascinosa",
            "largest_vessel_loa_m": Decimal("290.00"),
        },
        {
            "code": "ensenada",
            "name": "Ensenada",
            "commercial_name": "",
            "country": "Mexico",
            "region": "Baja California",
            "latitude": None,
            "longitude": None,
            "status": "operational",
            "min_berth_draft_m": Decimal("11.00"),
            "anchorage_slot_count": 0,
            "largest_vessel_recorded": "Ovation of the Seas",
            "largest_vessel_loa_m": Decimal("348.00"),
            "notes": "Coords TBD — doc copy error vs La Paz.",
        },
    ]

    port_by_code = {}
    for data in ports:
        notes = data.pop("notes", "")
        port = Port.objects.create(notes=notes, is_active=True, **data)
        port_by_code[port.code] = port

    la_paz = port_by_code["la_paz"]
    berth_lp = Berth.objects.create(
        port=la_paz,
        code="main",
        name="Main pier",
        length_m=Decimal("200.00"),
        width_m=Decimal("20.75"),
        min_draft_m=Decimal("11.00"),
        sort_order=1,
    )
    Position.objects.create(
        port=la_paz,
        berth=berth_lp,
        code="P1",
        position_type="pier",
        sort_order=1,
    )

    pp = port_by_code["puerto_plata"]
    berth_m12 = Berth.objects.create(
        port=pp,
        code="M1_M2",
        name="Muelles 1 y 2",
        length_m=Decimal("622.25"),
        width_m=Decimal("14.00"),
        min_draft_m=Decimal("11.00"),
        sort_order=1,
    )
    berth_m3 = Berth.objects.create(
        port=pp,
        code="M3",
        name="Muelle 3",
        length_m=Decimal("327.25"),
        width_m=Decimal("14.00"),
        min_draft_m=Decimal("11.00"),
        sort_order=2,
    )
    pos_e1 = Position.objects.create(
        port=pp, berth=berth_m12, code="E1", position_type="pier", sort_order=1
    )
    pos_e2 = Position.objects.create(
        port=pp, berth=berth_m12, code="E2", position_type="pier", sort_order=2
    )
    pos_w3 = Position.objects.create(
        port=pp, berth=berth_m3, code="W3", position_type="pier", sort_order=3
    )

    scenario_pp = MooringScenario.objects.create(
        port=pp,
        name="2 vessels — current layout",
        vessel_count=2,
        is_projection=False,
    )
    MooringScenarioSlot.objects.create(
        scenario=scenario_pp, position=pos_e1, slot_label="E1", max_loa_m=Decimal("365.00"), sort_order=1
    )
    MooringScenarioSlot.objects.create(
        scenario=scenario_pp, position=pos_w3, slot_label="W3", max_loa_m=Decimal("333.00"), sort_order=2
    )

    roatan = port_by_code["roatan"]
    berth_p1 = Berth.objects.create(
        port=roatan,
        code="P1",
        name="Pier P1",
        length_m=Decimal("180.00"),
        width_m=Decimal("10.50"),
        walkway_length_m=Decimal("30.00"),
        walkway_width_m=Decimal("10.00"),
        min_draft_m=Decimal("12.00"),
        sort_order=1,
    )
    berth_p2 = Berth.objects.create(
        port=roatan,
        code="P2",
        name="Pier P2",
        length_m=Decimal("250.00"),
        width_m=Decimal("10.50"),
        walkway_length_m=Decimal("30.00"),
        walkway_width_m=Decimal("10.00"),
        min_draft_m=Decimal("12.00"),
        sort_order=2,
    )
    pos_p1 = Position.objects.create(
        port=roatan, berth=berth_p1, code="P1", position_type="pier", sort_order=1
    )
    pos_p2 = Position.objects.create(
        port=roatan, berth=berth_p2, code="P2", position_type="pier", sort_order=2
    )
    pos_a1 = Position.objects.create(
        port=roatan, code="A1", position_type="anchorage", sort_order=3
    )
    pos_a2 = Position.objects.create(
        port=roatan, code="A2", position_type="anchorage", sort_order=4
    )

    scenario_ro = MooringScenario.objects.create(
        port=roatan,
        name="2 pier vessels — current",
        vessel_count=2,
        is_projection=False,
    )
    MooringScenarioSlot.objects.create(
        scenario=scenario_ro, position=pos_p1, slot_label="P1", max_loa_m=Decimal("365.00"), sort_order=1
    )
    MooringScenarioSlot.objects.create(
        scenario=scenario_ro, position=pos_p2, slot_label="P2", max_loa_m=Decimal("333.00"), sort_order=2
    )


def unseed_catalog(apps, schema_editor):
    Port = apps.get_model("catalogs", "Port")
    Port.objects.filter(
        code__in=[
            "la_paz",
            "puerto_plata",
            "cabo_rojo",
            "roatan",
            "samana",
            "melilla",
            "ensenada",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalogs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
