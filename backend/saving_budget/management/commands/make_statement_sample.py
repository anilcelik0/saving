import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from saving_budget.statements import samples


class Command(BaseCommand):
    help = (
        "Turn real statement files (PDF / XLSX) into masked fixtures for check_statements: names, addresses, "
        "card/IBAN/customer numbers and e-mails are masked, positions/amounts/dates kept. Verifies that the fixture "
        "reads like the original. Review once with --review; the original file can be deleted afterwards."
    )

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="+", help="Statement files (inside the container, e.g. statement_samples/raw/x.pdf)")
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR) / "statement_samples"))
        parser.add_argument("--mask", default="", help="Extra words to mask as names, comma separated")
        parser.add_argument("--name", default="", help="Fixture name (single file only); default bank-type-date-ext")
        parser.add_argument("--review", action="store_true", help="Print the masked text outside the rows")
        parser.add_argument("--force", action="store_true", help="Overwrite an existing fixture with the same name")

    def handle(self, *args, files, out, mask, name, review, force, **options):
        if name and len(files) > 1:
            raise CommandError("--name works with a single file.")
        out_dir = Path(out)
        out_dir.mkdir(parents=True, exist_ok=True)
        taken = {p.stem for p in out_dir.glob("*.json") if not p.name.endswith(".expected.json")}
        extra = [w.strip() for w in mask.split(",") if w.strip()]
        for file in files:
            fixture, original, counts = samples.make_fixture(file, extra)
            target_name = name or samples.sample_name(original, fixture["type"], set() if force else taken)
            target = out_dir / f"{target_name}.json"
            if target.exists() and not force:
                raise CommandError(f"{target} exists (use --force or --name).")
            try:
                masked = samples.parse_fixture(fixture)
            except Exception as exc:  # noqa: BLE001 - reported, the fixture is still written for inspection
                masked = None
                self.stdout.write(self.style.WARNING(f"  masked fixture could not be read: {exc}"))
            target.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
            taken.add(target_name)
            masked_counts = ", ".join(f"{k} {v}" for k, v in counts.items())
            self.stdout.write(self.style.MIGRATE_HEADING(f"{Path(file).name} -> {target.name}"))
            self.stdout.write(f"  masked: {masked_counts}")
            if diffs := samples.input_equal(original, masked):
                self.stdout.write(self.style.ERROR("  masking changed what the engine reads:"))
                for d in diffs:
                    self.stdout.write(f"    {d}")
            else:
                self.stdout.write(self.style.SUCCESS("  reads exactly like the original"))
            if review:
                for line in samples.review_lines(fixture):
                    self.stdout.write(f"    | {line}")
        self.stdout.write("Next: check_statements --accept after checking the result.")
