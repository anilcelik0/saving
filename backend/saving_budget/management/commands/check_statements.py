import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from saving_budget.statements import samples
from saving_budget.statements.base import StatementParseError


class Command(BaseCommand):
    help = (
        "Read every statement sample fixture (statement_samples/*.json, see make_statement_sample) and compare the "
        "result with its <name>.expected.json: run after every engine change. --accept stores the current result "
        "as expected (only after checking the differences)."
    )

    def add_arguments(self, parser):
        parser.add_argument("names", nargs="*", help="Only these samples (fixture names without .json)")
        parser.add_argument("--dir", default=str(Path(settings.BASE_DIR) / "statement_samples"))
        parser.add_argument("--accept", action="store_true", help="Store current results as expected")
        parser.add_argument("--lines", action="store_true", help="Print every line of each sample")

    def handle(self, *args, names, dir, accept, lines, **options):
        folder = Path(dir)
        fixtures = sorted(p for p in folder.glob("*.json") if not p.name.endswith(".expected.json"))
        if names:
            fixtures = [p for p in fixtures if p.stem in names]
        if not fixtures:
            raise CommandError(f"No fixtures in {folder} (make_statement_sample creates them).")
        changed = errors = 0
        totals = {"ok": 0, "mismatch": 0, "unknown": 0}
        for path in fixtures:
            expected_path = path.with_name(f"{path.stem}.expected.json")
            try:
                result = samples.parse_fixture(samples.load_fixture(path))
                actual = samples.summarize(result)
            except StatementParseError as exc:
                actual = {"error": str(exc)}
            except Exception as exc:  # noqa: BLE001 - an engine crash is a result to report
                errors += 1
                self.stdout.write(self.style.ERROR(f"{path.stem:44} CRASH {type(exc).__name__}: {exc}"))
                continue
            status = actual.get("check_status", "error")
            totals[status] = totals.get(status, 0) + 1
            info = (f"{status:8} n={actual.get('line_count', 0):<3} gider={actual.get('expense')} "
                    f"gelir={actual.get('income')} {' '.join(actual.get('checks', []))}")
            if expected_path.exists():
                diffs = samples.compare(json.loads(expected_path.read_text(encoding="utf-8")), actual) \
                    if "error" not in actual else ["error: " + actual["error"]]
                label = self.style.SUCCESS("same   ") if not diffs else self.style.WARNING("CHANGED")
            else:
                diffs, label = [], self.style.NOTICE("NEW    ")
            self.stdout.write(f"{path.stem:44} {label} {info}")
            for d in diffs:
                self.stdout.write(f"      {d}")
            if lines:
                for row in actual.get("lines", []):
                    self.stdout.write(f"      . {row}")
            if diffs or not expected_path.exists():
                changed += 1
                if accept:
                    expected_path.write_text(json.dumps(actual, ensure_ascii=False, indent=1), encoding="utf-8")
        summary = ", ".join(f"{k} {v}" for k, v in totals.items() if v)
        self.stdout.write(f"{len(fixtures)} sample(s): {summary}; {changed} changed/new, {errors} crashed"
                          + (" (accepted)" if accept and changed else ""))
        if errors or (changed and not accept):
            raise CommandError("Differences found: check them, then run with --accept.")
