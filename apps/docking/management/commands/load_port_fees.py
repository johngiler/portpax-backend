"""
Carga tarifas portuarias por pasajero (Port Fees 25-26).

Datos tomados del PDF "Port Fees 25-26": Costa Maya, Roatan, Puerto Plata, Cabo Rojo, Pichilingue.
Período May'25 - Apr'26. Crea puertos si no existen y reglas PortFeeRule por fee_tier (RCL, NCL, MSC, CCL, VV, Others).

Uso:
  python manage.py load_port_fees
  python manage.py load_port_fees --dry-run
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.docking.models import Port, PortFeeRule, ShippingLine

# Datos del PDF Port Fees 25-26 (USD por pasajero). May'25 - Apr'26
PORT_FEES_25_26 = [
    {
        "port_name": "Costa Maya",
        "port_code": "COZ",
        "fees": {"RCL": "12.52", "NCL": "14.64", "MSC": "14.60", "VV": "15.73", "CCL": "15.73", "Others": "15.73"},
        "notes": "NCL Loyalty Fee $3.00 USD Per Pax (applicable).",
    },
    {
        "port_name": "Roatan",
        "port_code": "POR",
        "fees": {"RCL": "12.52", "NCL": "14.64", "MSC": "13.60", "VV": "15.73", "CCL": "15.73", "Others": "15.73"},
        "notes": "Taxes: IHT $2.67, Zolitur $2.00 per pax. Port improvement $0.50 (+15% VAT).",
    },
    {
        "port_name": "Puerto Plata",
        "port_code": "POP",
        "fees": {"RCL": "12.52", "NCL": "14.64", "MSC": "12.70", "CCL": "15.73", "VV": "15.73", "Others": "15.73"},
        "notes": "APORDOM $2.00 per pax. NCL Loyalty Fee $3.00 per pax.",
    },
    {
        "port_name": "Cabo Rojo",
        "port_code": "CRO",
        "fees": {"RCL": "15.73", "NCL": "14.64", "MSC": "15.73", "VV": "15.73", "CCL": "15.73", "Others": "15.73"},
        "notes": "APORDOM $1.50 per pax.",
    },
    {
        "port_name": "Pichilingue",
        "port_code": "PCH",
        "fees": {"RCL": "15.20", "NCL": "15.20", "MSC": "15.20", "VV": "15.20", "CCL": "13.89", "Others": "15.20"},
        "notes": "",
    },
]

VALID_FROM = date(2025, 5, 1)
VALID_TO = date(2026, 4, 30)

# Mapeo nombre naviera (contains) -> fee_tier para aplicar tarifas
NAVIERA_FEE_TIER = [
    ("royal caribbean", "RCL"),
    ("celebrity", "RCL"),
    ("norwegian", "NCL"),
    ("ncl ", "NCL"),
    ("regent", "NCL"),
    ("oceania", "NCL"),
    ("msc", "MSC"),
    ("carnival", "CCL"),
    ("costa", "CCL"),
    ("virgin", "VV"),
    ("virgin voyages", "VV"),
]


class Command(BaseCommand):
    help = "Carga tarifas portuarias 25-26 (Costa Maya, Roatan, Puerto Plata, Cabo Rojo, Pichilingue)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="No guardar cambios")
        parser.add_argument(
            "--skip-fee-tier",
            action="store_true",
            help="No actualizar fee_tier en navieras",
        )

    def _assign_fee_tiers(self, dry_run):
        """Asigna fee_tier a navieras conocidas para aplicar tarifas."""
        updated = 0
        for line in ShippingLine.objects.all():
            name_lower = (line.name or "").lower()
            tier = "Others"
            for key, value in NAVIERA_FEE_TIER:
                if key in name_lower:
                    tier = value
                    break
            if line.fee_tier != tier:
                if not dry_run:
                    line.fee_tier = tier
                    line.save(update_fields=["fee_tier"])
                updated += 1
        return updated

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        skip_fee_tier = options["skip_fee_tier"]
        created_ports = 0
        created_rules = 0
        updated_rules = 0

        for item in PORT_FEES_25_26:
            port_name = item["port_name"]
            port_code = item["port_code"]
            fees = item["fees"]
            notes = item.get("notes", "")

            if dry_run:
                self.stdout.write(f"  [DRY-RUN] Puerto: {port_name} ({port_code})")
                for tier, amount in fees.items():
                    self.stdout.write(f"    {tier}: ${amount}")
                continue

            port = Port.objects.filter(code=port_code).first() or Port.objects.filter(
                name__iexact=port_name
            ).first()
            if not port:
                port = Port.objects.create(name=port_name, code=port_code)
                created_ports += 1
            elif not port.code:
                port.code = port_code
                port.save(update_fields=["code"])
            if port.name != port_name:
                port.name = port_name
                port.save(update_fields=["name"])

            for fee_tier, amount_str in fees.items():
                amount = Decimal(amount_str)
                rule = PortFeeRule.objects.filter(port=port, fee_tier=fee_tier).first()
                if rule:
                    if rule.amount_per_pax_usd != amount or rule.valid_from != VALID_FROM:
                        rule.amount_per_pax_usd = amount
                        rule.valid_from = VALID_FROM
                        rule.valid_to = VALID_TO
                        rule.notes = notes
                        rule.save()
                        updated_rules += 1
                else:
                    PortFeeRule.objects.create(
                        port=port,
                        fee_tier=fee_tier,
                        amount_per_pax_usd=amount,
                        valid_from=VALID_FROM,
                        valid_to=VALID_TO,
                        notes=notes,
                    )
                    created_rules += 1

        if not skip_fee_tier and not dry_run:
            tier_updated = self._assign_fee_tiers(dry_run=False)
            if tier_updated:
                self.stdout.write(self.style.SUCCESS(f"Navieras con fee_tier asignado: {tier_updated}."))

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Port Fees: {created_ports} puertos creados, {created_rules} reglas nuevas, {updated_rules} reglas actualizadas."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("[DRY-RUN] Tarifas no guardadas."))