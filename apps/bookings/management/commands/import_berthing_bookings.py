from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.bookings.services.confirmation_pdf import generate_confirmation_pdfs
from apps.bookings.services.import_berthing.runner import (
    import_berthing_rows,
    load_rows_from_json,
    parse_and_write_json,
)


DEFAULT_JSON = Path(settings.BASE_DIR) / "data" / "berthing_bookings.json"
DEFAULT_XLSX = (
    Path(settings.BASE_DIR).parent
    / "docs"
    / "Archivos Matriz (Fernanada)"
    / "BERTHING PAPERS"
)
DEFAULT_REPORT = Path(settings.BASE_DIR) / "data" / "berthing_bookings_import_report.json"


class Command(BaseCommand):
    help = (
        "Import historic berthing bookings from JSON (or regenerate JSON from Excel). "
        "Use --delete-data to clear all Booking rows before import. "
        "Use --only-generate-confirmation to backfill CO/CL confirmation PDFs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--data",
            type=str,
            default=str(DEFAULT_JSON),
            help="Path to berthing_bookings.json",
        )
        parser.add_argument(
            "--from-xlsx",
            type=str,
            nargs="?",
            const=str(DEFAULT_XLSX),
            default=None,
            help="Parse BERTHING PAPERS folder and write JSON before import",
        )
        parser.add_argument(
            "--delete-data",
            action="store_true",
            help="Delete all Booking rows before import",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate rows only; do not write bookings",
        )
        parser.add_argument(
            "--parse-only",
            action="store_true",
            help="Only regenerate JSON from Excel; skip DB import",
        )
        parser.add_argument(
            "--only-generate-confirmation",
            action="store_true",
            help=(
                "Skip import; generate confirmation PDFs for existing CO/CL bookings "
                "that do not have a file yet (use --force-confirmation to regenerate all)."
            ),
        )
        parser.add_argument(
            "--force-confirmation",
            action="store_true",
            help="Regenerate confirmation PDFs even when a file already exists.",
        )
        parser.add_argument(
            "--skip-confirmation",
            action="store_true",
            help="During import, do not generate confirmation PDFs.",
        )

    def handle(self, *args, **options):
        only_confirmation = options["only_generate_confirmation"]
        force_confirmation = options["force_confirmation"]

        if only_confirmation:
            self.stdout.write(
                "Generating confirmation PDFs for CO/CL bookings "
                f"({'force' if force_confirmation else 'missing only'}) …"
            )
            report = generate_confirmation_pdfs(only_missing=not force_confirmation)
            DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
            payload = {"mode": "only_generate_confirmation", "confirmations": report}
            DEFAULT_REPORT.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stdout.write(json.dumps(payload, indent=2))
            self.stdout.write(self.style.SUCCESS(f"Report → {DEFAULT_REPORT}"))
            if report["error_count"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"Generated {report['generated']} with {report['error_count']} errors."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Generated {report['generated']} confirmation PDF(s).")
                )
            return

        data_path = Path(options["data"])
        xlsx_folder = options["from_xlsx"]
        delete_data = options["delete_data"]
        dry_run = options["dry_run"]
        parse_only = options["parse_only"]
        skip_confirmation = options["skip_confirmation"]

        if xlsx_folder or parse_only:
            folder = Path(xlsx_folder or DEFAULT_XLSX)
            if not folder.is_dir():
                raise CommandError(f"Excel folder not found: {folder}")
            self.stdout.write(f"Parsing Excel from {folder} …")
            rows = parse_and_write_json(folder, data_path)
            self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} rows → {data_path}"))
            if parse_only:
                return
        else:
            if not data_path.is_file():
                raise CommandError(
                    f"Data file not found: {data_path}. "
                    "Run with --from-xlsx to generate it from BERTHING PAPERS."
                )
            rows = load_rows_from_json(data_path)
            self.stdout.write(f"Loaded {len(rows)} rows from {data_path}")

        report = import_berthing_rows(
            rows,
            delete_data=delete_data,
            dry_run=dry_run,
            generate_confirmations=not dry_run and not skip_confirmation,
            force_confirmation=force_confirmation,
        )
        DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        printable = {k: v for k, v in report.items() if k != "invalid_rows"}
        self.stdout.write(json.dumps(printable, indent=2))
        self.stdout.write(self.style.SUCCESS(f"Report → {DEFAULT_REPORT}"))

        if not dry_run:
            valid = report["parsed"] - report["invalid"]
            done = report["created"] + report["updated"]
            if done != valid:
                self.stdout.write(
                    self.style.WARNING(
                        f"Coverage mismatch: created+updated={done} valid={valid}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Imported all {valid} valid rows.")
                )
            conf = report.get("confirmations") or {}
            if not conf.get("skipped"):
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Confirmations generated: {conf.get('generated', 0)}"
                    )
                )
                if conf.get("error_count"):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Confirmation errors: {conf['error_count']}"
                        )
                    )
