r"""
Importa el Catálogo de barcos (Calendar 2026 - Catalogo.csv).

Columnas esperadas: NUM, CLAVE BARCO, BARCO, NAVIERA, CAPACIDAD, TONELAJE, ESLORA mts, CALADO.
- Crea o actualiza Navieras (NAVIERA) y Barcos (BARCO) con code=CLAVE BARCO, capacity_pax, length_m, draft_m.
- Si un barco ya existe por nombre o por code, se actualiza.

Uso:
  python manage.py load_catalog "/ruta/a/Calendar 2026.xlsx - Catalogo.csv"
  python manage.py load_catalog /ruta/al/catalogo.csv --dry-run
"""
import csv
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.docking.models import Ship, ShippingLine


def parse_int(s):
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    s = str(s).strip().replace(",", "").replace(" ", "")
    try:
        return int(s)
    except ValueError:
        return None


def parse_decimal(s):
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    s = str(s).strip().replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


class Command(BaseCommand):
    help = "Importa catálogo de barcos (CLAVE BARCO, BARCO, NAVIERA, CAPACIDAD, ESLORA mts, CALADO)."

    def add_arguments(self, parser):
        parser.add_argument("catalog_csv", nargs="?", help="Ruta al CSV del catálogo")
        parser.add_argument("--dry-run", action="store_true", help="No guardar cambios")

    def handle(self, *args, **options):
        path = options.get("catalog_csv")
        if not path:
            self.stdout.write(self.style.ERROR("Indica la ruta al CSV del catálogo."))
            return
        dry_run = options["dry_run"]

        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Archivo no encontrado: {path}"))
            return

        # Buscar fila de cabecera (contiene CLAVE BARCO o BARCO)
        header_idx = None
        for i, row in enumerate(rows):
            row_str = " ".join(str(c).upper() for c in row)
            if "CLAVE BARCO" in row_str or ("BARCO" in row_str and "NAVIERA" in row_str):
                header_idx = i
                break
        if header_idx is None:
            self.stdout.write(self.style.ERROR("No se encontró cabecera con CLAVE BARCO / BARCO / NAVIERA."))
            return

        header = [str(c).strip().upper() for c in rows[header_idx]]
        col_num = next((i for i, h in enumerate(header) if "NUM" in h and "CLAVE" not in h), 2)
        col_clave = next((i for i, h in enumerate(header) if "CLAVE" in h and "BARCO" in h), 3)
        col_barco = next((i for i, h in enumerate(header) if h == "BARCO"), 4)
        col_naviera = next((i for i, h in enumerate(header) if "NAVIERA" in h), 5)
        col_capacidad = next((i for i, h in enumerate(header) if "CAPACIDAD" in h), 6)
        col_eslora = next((i for i, h in enumerate(header) if "ESLORA" in h and "MTS" in h), 8)
        col_calado = next((i for i, h in enumerate(header) if "CALADO" in h), 11)

        created_lines = 0
        created_ships = 0
        updated_ships = 0

        for row in rows[header_idx + 1 :]:
            if len(row) <= max(col_barco, col_naviera):
                continue
            clave = str(row[col_clave]).strip() if col_clave < len(row) else ""
            barco = str(row[col_barco]).strip() if col_barco < len(row) else ""
            naviera = str(row[col_naviera]).strip() if col_naviera < len(row) else ""
            if not barco and not clave:
                continue
            name = barco or clave
            capacity = parse_int(row[col_capacidad]) if col_capacidad < len(row) else None
            length_m = parse_decimal(row[col_eslora]) if col_eslora < len(row) else None
            draft_m = parse_decimal(row[col_calado]) if col_calado < len(row) else None

            if dry_run:
                self.stdout.write(f"  [DRY-RUN] {clave or name} | {name} | {naviera}")
                created_ships += 1
                continue

            # Naviera
            if naviera:
                line = ShippingLine.objects.filter(name__iexact=naviera).first()
                if not line:
                    line = ShippingLine.objects.create(
                        name=naviera,
                        code=naviera[:20].upper().replace(" ", "_").replace(".", ""),
                    )
                    created_lines += 1
                elif line.name != naviera:
                    line.name = naviera
                    line.save(update_fields=["name"])
            else:
                line = ShippingLine.objects.filter(name__iexact="Sin naviera").first()
                if not line:
                    line = ShippingLine.objects.create(name="Sin naviera", code="SIN_NAVIERA")
                    created_lines += 1

            # Barco: buscar por code o por name
            ship = None
            if clave:
                ship = Ship.objects.filter(code=clave).first()
            if not ship and name:
                ship = Ship.objects.filter(name__iexact=name).first()
            if not ship:
                ship = Ship.objects.filter(shipping_line=line, name__iexact=name).first()

            if ship:
                updated = False
                if ship.code != clave and clave:
                    ship.code = clave
                    updated = True
                if ship.shipping_line_id != line.id:
                    ship.shipping_line = line
                    updated = True
                if capacity is not None and ship.capacity_pax != capacity:
                    ship.capacity_pax = capacity
                    updated = True
                if length_m is not None and ship.length_m != length_m:
                    ship.length_m = length_m
                    updated = True
                if draft_m is not None and ship.draft_m != draft_m:
                    ship.draft_m = draft_m
                    updated = True
                if ship.name != name:
                    ship.name = name
                    updated = True
                if updated:
                    ship.save()
                    updated_ships += 1
            else:
                Ship.objects.create(
                    shipping_line=line,
                    name=name,
                    code=clave or "",
                    capacity_pax=capacity,
                    length_m=length_m,
                    draft_m=draft_m,
                )
                created_ships += 1

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Catálogo: {created_lines} navieras nuevas, {created_ships} barcos nuevos, {updated_ships} barcos actualizados."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"[DRY-RUN] Procesadas filas de catálogo."))