import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from lineup_cards import importer, services
from lineup_cards.models import (Attribute, Card, CardImport, CardType, CardTypeAttribute, CardTypeField, CardValue,
                                 Tag)

DATASETS = Path(__file__).resolve().parents[2] / "datasets"
DATASET_ONLY_KEYS = {"sources"}  # per-value source links: set here, not import columns


class Command(BaseCommand):
    help = (
        "Loads the Line Up card sets in lineup_cards/datasets/*.json (built from their sources by "
        "datasets/build_sets.py) through the import pipeline and approves them; each file also defines its card type "
        "(attributes, display fields). --reset first deletes the whole card pool and the game data frozen on it "
        "(daily puzzles with their plays, challenges; runs being played are abandoned). --dry-run rolls back."
    )

    def add_arguments(self, parser):
        parser.add_argument("sets", nargs="*", help="Set names, e.g. provinces films (default: every file)")
        parser.add_argument("--reset", action="store_true",
                            help="Delete every card (demo ones too) and the game data that points at them first")
        parser.add_argument("--dry-run", action="store_true", help="Do everything, then roll back")

    def handle(self, *args, sets, reset, dry_run, **options):
        paths = [DATASETS / f"{name}.json" for name in sets] if sets else sorted(DATASETS.glob("*.json"))
        missing = [p.name for p in paths if not p.exists()]
        if missing or not paths:
            raise CommandError(f"Set dosyası yok: {', '.join(missing) or DATASETS}")
        with transaction.atomic():
            if reset:
                self._reset()
            for path in paths:
                self._load(path)
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("--dry-run: hiçbir şey kaydedilmedi (geri alındı)."))

    # ------------------------------------------------------------ reset
    def _reset(self):
        # Game models are imported here only: frozen decks hold card ids, so a reset has to clear them too.
        from lineup_games.models import DailyPuzzle, Run
        from lineup_social.models import Challenge

        now = timezone.now()
        cards = Card.objects.count()
        Card.objects.all().delete()  # values cascade; moves keep their row with an empty card
        imports, _ = CardImport.objects.all().delete()
        puzzles = DailyPuzzle.objects.count()
        DailyPuzzle.objects.all().delete()  # plays cascade; today's puzzle is rebuilt from the new pool
        challenges = Challenge.objects.count()
        Challenge.objects.all().delete()
        abandoned = Run.objects.filter(status=Run.Status.PLAYING).update(status=Run.Status.ABANDONED, finished_at=now)
        tags, _ = Tag.objects.filter(cards__isnull=True, children__isnull=True).delete()
        self.stdout.write(self.style.WARNING(
            f"Sıfırlandı: {cards} kart, {imports} içe aktarma, {puzzles} günlük bulmaca, {challenges} meydan okuma "
            f"silindi; {abandoned} süren tur kapatıldı; {tags} boş etiket silindi."))

    # ------------------------------------------------------------ load
    def _load(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        card_type = self._ensure_type(data["definition"])
        cards = data["cards"]
        sources = {c["external_key"]: c.get("sources", {}) for c in cards}
        rows_in = [{k: v for k, v in c.items() if k not in DATASET_ONLY_KEYS} for c in cards]

        raw_rows = importer.read_json(json.dumps({"cards": rows_in}, ensure_ascii=False).encode("utf-8"))
        results, file_warnings = importer.validate(card_type, raw_rows)
        errors = [f"satır {r.number} ({r.data.get('title')}): {'; '.join(r.errors)}" for r in results if r.errors]
        if errors:
            raise CommandError(f"{path.name}: {len(errors)} hatalı satır, hiçbiri yüklenmedi:\n" + "\n".join(errors))
        rows = importer.to_json(results)
        counts = importer.apply(card_type, rows)
        CardImport.objects.create(
            card_type=card_type, file_name=path.name, status=CardImport.Status.APPLIED, rows=rows,
            file_warnings=file_warnings, summary=importer.summarize(results), result=counts, applied_at=timezone.now())

        for key, per_value in sources.items():
            for attribute_key, url in per_value.items():
                CardValue.objects.filter(card__card_type=card_type, card__external_key=key,
                                         attribute__key=attribute_key).update(source_url=url)

        loaded = Card.objects.filter(card_type=card_type, external_key__in=list(sources)) \
            .prefetch_related(*services.REVIEW_PREFETCH)
        approved, skipped = services.set_status(loaded, Card.Status.APPROVED)
        unchanged = sum(r.action == "unchanged" for r in results)
        self.stdout.write(self.style.SUCCESS(
            f"{path.name} → {card_type}: {counts['created']} yeni, {counts['updated']} güncel, {unchanged} aynı; "
            f"{approved} onaylandı."))
        for card, problems in skipped:
            self.stdout.write(self.style.ERROR(f"  onaylanamadı: {card.title}: {' '.join(problems)}"))
        warnings = [f"  {r.data['title']}: {w}" for r in results for w in r.warnings]
        for line in file_warnings + warnings:
            self.stdout.write(f"  uyarı: {line.strip()}")

    def _ensure_type(self, definition: dict) -> CardType:
        """The card type, its attributes (shared by key) and display fields as the set file defines them."""
        card_type, _ = CardType.objects.update_or_create(key=definition["key"], defaults={
            "name": definition["name"], "emoji": definition["emoji"], "description": definition["description"]})
        keep_attributes = []
        for order, spec in enumerate(definition["attributes"]):
            attribute = Attribute.objects.filter(key=spec["key"]).first()
            if attribute and attribute.value_type != spec["value_type"]:
                raise CommandError(f"Nitelik {spec['key']} zaten {attribute.value_type} tipinde, set {spec['value_type']} "
                                   "istiyor.")
            attribute, _ = Attribute.objects.update_or_create(key=spec["key"], defaults={
                "name": spec["name"], "value_type": spec["value_type"], "unit": spec["unit"],
                "decimal_places": spec["decimal_places"], "lower_label": spec["lower_label"],
                "higher_label": spec["higher_label"], "is_active": True})
            CardTypeAttribute.objects.update_or_create(card_type=card_type, attribute=attribute, defaults={
                "is_required": spec["required"], "order": order})
            keep_attributes.append(attribute.pk)
        # Schema entries the set no longer has go, unless a card of the type still holds such a value.
        stale = card_type.schema_attributes.exclude(attribute_id__in=keep_attributes)
        for entry in stale:
            if not CardValue.objects.filter(card__card_type=card_type, attribute=entry.attribute).exists():
                entry.delete()
        keep_fields = []
        for order, spec in enumerate(definition["fields"]):
            CardTypeField.objects.update_or_create(card_type=card_type, key=spec["key"], defaults={
                "label": spec["label"], "is_required": spec["required"], "order": order})
            keep_fields.append(spec["key"])
        for field in card_type.fields.exclude(key__in=keep_fields):
            if not card_type.cards.filter(extra__has_key=field.key).exists():
                field.delete()
        return card_type
