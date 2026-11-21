"""
Card import pipeline, the single way cards enter the pool in bulk. Rows come from an uploaded Excel/CSV today and
from source adapters (Wikidata, Phase 7) later; both are normalized and validated against a card type's schema here,
previewed in the admin (CardImport), then applied as an upsert by external key (or title when the key is empty).

Columns are machine keys: base columns + the type's attribute keys + its extra field keys.
Dates: 1453 · 1453-05 · 1453-05-29 · 29.05.1453 · 05.1453 · -1200 / MÖ 1200. Numbers: 4479525 · 4.479.525 · 11891,5.
"""

import csv
import io
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from . import services, values
from .models import Attribute, Card, CardType, CardValue, Tag

MAX_ROWS = 5000
BASE_COLUMNS = [
    ("external_key", "Kaynaktaki kimlik (ör. wikidata:Q406). Boşsa aynı başlıklı kart güncellenir."),
    ("title", "Başlık (zorunlu)"),
    ("subtitle", "Alt başlık (ör. sanatçı)"),
    ("title_lang", "Başlık dili; boşsa tr. Onay için tr gerekir."),
    ("popularity", "Tanınırlık 0-100; boşsa 50"),
    ("tags", "Etiketler, virgülle: Futbol, Galatasaray"),
    ("source_url", "Kaynak bağlantısı (isteğe bağlı)"),
]
BASE_KEYS = [key for key, _ in BASE_COLUMNS]
DATE_PATTERNS = [
    re.compile(r"^(?P<y>-?\d{1,4})(?:-(?P<m>\d{1,2})(?:-(?P<d>\d{1,2}))?)?$"),  # 1453 / 1453-05 / 1453-05-29
    re.compile(r"^(?:(?P<d>\d{1,2})\.)?(?P<m>\d{1,2})\.(?P<y>-?\d{1,4})$"),  # 29.05.1453 / 05.1453
]


@dataclass
class RowResult:
    number: int
    action: str = "create"  # create | update | unchanged | error
    data: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)  # attribute key -> {"number": str} or {"year", "month", "day"}
    display: str = ""
    card_id: str | None = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------- template
def columns(card_type: CardType) -> list[tuple[str, str]]:
    """(key, explanation) for every column of the type's template."""
    result = list(BASE_COLUMNS)
    for entry in card_type.schema_attributes.select_related("attribute"):
        a = entry.attribute
        kind = "tarih: 1453, 1453-05, 1453-05-29, MÖ için -1200" if a.value_type == Attribute.ValueType.DATE \
            else f"sayı{f' ({a.unit})' if a.unit else ''}, en fazla {a.decimal_places} ondalık"
        result.append((a.key, f"{a.name}: {kind}{' (zorunlu)' if entry.is_required else ''}"))
    for f in card_type.fields.all():
        result.append((f.key, f"{f.label} (ek bilgi{', zorunlu' if f.is_required else ''})"))
    return result


def build_template(card_type: CardType) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    cols = columns(card_type)
    wb = Workbook()
    sheet = wb.active
    sheet.title = "kartlar"
    sheet.append([key for key, _ in cols])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    help_sheet = wb.create_sheet("açıklama")
    help_sheet.append(["sütun", "açıklama"])
    for key, text in cols:
        help_sheet.append([key, text])
    help_sheet.append([])
    help_sheet.append(["", "İlk sayfadaki başlık satırını değiştirmeyin; her satır bir kart."])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------- reading
def read_file(name: str, content: bytes) -> list[dict]:
    """Rows as {column key: raw value}; raises ValueError (Turkish) for unreadable files."""
    lower = name.lower()
    if lower.endswith(".xlsx"):
        from openpyxl import load_workbook
        try:
            sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).worksheets[0]
        except Exception as e:
            raise ValueError(f"Excel dosyası okunamadı: {e}") from None
        rows = list(sheet.iter_rows(values_only=True))
    elif lower.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text.strip() else csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
    else:
        raise ValueError("Yalnızca .xlsx veya .csv yüklenebilir.")
    if not rows:
        raise ValueError("Dosya boş.")
    header = [str(h or "").strip().lower() for h in rows[0]]
    body = [r for r in rows[1:] if any(str(v).strip() for v in r if v is not None)]
    if len(body) > MAX_ROWS:
        raise ValueError(f"En fazla {MAX_ROWS} satır içe aktarılabilir (dosyada {len(body)}).")
    return [{h: (r[i] if i < len(r) else None) for i, h in enumerate(header) if h} for r in body]


def _text(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    return str(raw).strip()


def parse_date(raw) -> tuple[int, int | None, int | None]:
    if isinstance(raw, datetime | date):
        return raw.year, raw.month, raw.day
    text = _text(raw).upper().replace(" ", "")
    bc = text.startswith("MÖ") or text.startswith("M.Ö.")
    text = text.removeprefix("M.Ö.").removeprefix("MÖ")
    for pattern in DATE_PATTERNS:
        match = pattern.match(text)
        if match:
            year = int(match["y"])
            month = int(match["m"]) if match["m"] else None
            day = int(match["d"]) if match["d"] else None
            return (-abs(year) if bc else year), month, day
    raise ValueError(f"Tarih anlaşılamadı: '{_text(raw)}' (ör. 1453, 1453-05-29, -1200)")


def parse_number(raw) -> Decimal:
    if isinstance(raw, int | float | Decimal) and not isinstance(raw, bool):
        return Decimal(str(raw))
    text = _text(raw).replace(" ", "").replace(" ", "")
    if "," in text and "." in text:
        thousands, decimal = (".", ",") if text.rfind(",") > text.rfind(".") else (",", ".")
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text:
        text = text.replace(",", ".") if text.count(",") == 1 else text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Sayı anlaşılamadı: '{_text(raw)}'") from None


# ---------------------------------------------------------------- validation
def validate(card_type: CardType, raw_rows: list[dict]) -> tuple[list[RowResult], list[str]]:
    schema = {e.attribute.key: e for e in card_type.schema_attributes.select_related("attribute")}
    field_keys = [f.key for f in card_type.fields.all()]
    known = set(BASE_KEYS) | set(schema) | set(field_keys)
    file_warnings = []
    if raw_rows:
        unknown = sorted(set(raw_rows[0]) - known)
        if unknown:
            file_warnings.append(f"Bilinmeyen sütunlar yok sayıldı: {', '.join(unknown)}")
        if "title" not in raw_rows[0]:
            file_warnings.append("'title' sütunu yok: şablonu kart türü sayfasından indirin.")

    existing = list(card_type.cards.prefetch_related("values__attribute"))
    by_key = {c.external_key: c for c in existing if c.external_key}
    by_title: dict[str, list[Card]] = {}
    for c in existing:
        by_title.setdefault(c.title.casefold(), []).append(c)
    url_validator = URLValidator()
    seen = set()
    results = []

    for number, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        row = RowResult(number=number)
        title = _text(raw.get("title"))
        key = _text(raw.get("external_key"))
        data = {"external_key": key, "title": title, "subtitle": _text(raw.get("subtitle")),
                "title_lang": (_text(raw.get("title_lang")) or "tr").lower(), "source_url": _text(raw.get("source_url")),
                "tags": [t.strip() for t in _text(raw.get("tags")).split(",") if t.strip()],
                "extra": {k: _text(raw.get(k)) for k in field_keys if _text(raw.get(k))}}
        if not title:
            row.errors.append("Başlık boş.")
        identity = key or title.casefold()
        if identity and identity in seen:
            row.errors.append("Bu kart dosyada iki kez var.")
        seen.add(identity)
        popularity = _text(raw.get("popularity"))
        try:
            data["popularity"] = int(parse_number(popularity)) if popularity else 50
            if not 0 <= data["popularity"] <= 100:
                raise ValueError
        except ValueError:
            row.errors.append(f"Tanınırlık 0-100 arası tam sayı olmalı: '{popularity}'.")
        if data["source_url"]:
            try:
                url_validator(data["source_url"])
            except ValidationError:
                row.errors.append("Kaynak geçerli bir bağlantı değil.")

        shown = []
        for attr_key, entry in schema.items():
            attribute, cell = entry.attribute, raw.get(attr_key)
            if not _text(cell) and not isinstance(cell, datetime | date):
                continue
            try:
                if attribute.value_type == Attribute.ValueType.DATE:
                    y, m, d = parse_date(cell)
                    problems = values.date_problems(y, m, d)
                    if problems:
                        raise ValueError(" ".join(problems))
                    row.values[attr_key] = {"year": y, "month": m, "day": d}
                    shown.append(f"{attribute.name}: {values.format_date(y, m, d)}")
                else:
                    n = parse_number(cell)
                    if values.decimal_places_of(n) > attribute.decimal_places:
                        raise ValueError(f"en fazla {attribute.decimal_places} ondalık")
                    row.values[attr_key] = {"number": str(n)}
                    shown.append(f"{attribute.name}: "
                                 f"{values.format_number(n, attribute.decimal_places, attribute.unit)}")
            except ValueError as e:
                row.errors.append(f"{attribute.name}: {e}")
        row.display = " · ".join(shown)
        missing = [e.attribute.name for k, e in schema.items() if e.is_required and k not in row.values]
        if data["title_lang"] != "tr":
            row.warnings.append("Türkçe başlık değil: onaylanamaz.")

        card = by_key.get(key) if key else None
        if card is None and not key:
            matches = by_title.get(title.casefold(), [])
            if len(matches) > 1:
                row.errors.append("Aynı başlıkta birden çok kart var: external_key girin.")
            card = matches[0] if len(matches) == 1 else None
        if card is not None:
            row.card_id = str(card.pk)
            stored = {v.attribute.key: v for v in card.values.all()}
            missing = [m for m in missing if not any(s.attribute.name == m for s in stored.values())]
        if missing:
            row.warnings.append(f"Eksik değer ({', '.join(missing)}): onay beklerken tamamlanmalı.")

        row.data = data
        if row.errors:
            row.action = "error"
        elif card is None:
            row.action = "create"
        else:
            row.action = "update" if _changes(card, data, row.values) else "unchanged"
        results.append(row)
    return results, file_warnings


def _changes(card: Card, data: dict, new_values: dict) -> bool:
    if (card.title, card.subtitle, card.title_lang, card.popularity) != (
            data["title"], data["subtitle"], data["title_lang"], data["popularity"]):
        return True
    if data["source_url"] and data["source_url"] != card.source_url:
        return True
    if any(card.extra.get(k) != v for k, v in data["extra"].items()):
        return True
    stored = {v.attribute.key: v for v in card.values.all()}
    for key, new in new_values.items():
        old = stored.get(key)
        if old is None:
            return True
        if "number" in new and Decimal(new["number"]) != old.number:
            return True
        if "year" in new and (new["year"], new["month"], new["day"]) != (old.year, old.month, old.day):
            return True
    existing_tags = {t.name.casefold() for t in card.tags.all()}
    return any(t.casefold() not in existing_tags for t in data["tags"])


def summarize(results: list[RowResult]) -> dict:
    summary = {"create": 0, "update": 0, "unchanged": 0, "error": 0}
    for r in results:
        summary[r.action] += 1
    return summary


def to_json(results: list[RowResult]) -> list[dict]:
    return [asdict(r) for r in results]


# ---------------------------------------------------------------- apply
@transaction.atomic
def apply(card_type: CardType, rows: list[dict]) -> dict:
    """Create/update the cards of valid rows. New cards and changed approved cards go to staging (review again)."""
    attributes = {e.attribute.key: e.attribute for e in card_type.schema_attributes.select_related("attribute")}
    now = timezone.now()
    counts = {"created": 0, "updated": 0}
    for row in rows:
        if row["action"] not in ("create", "update"):
            continue
        data = row["data"]
        card = Card.objects.select_for_update().get(pk=row["card_id"]) if row["card_id"] else \
            Card(card_type=card_type, external_key=data["external_key"])
        card.title, card.subtitle, card.title_lang = data["title"], data["subtitle"], data["title_lang"]
        card.popularity = data["popularity"]
        if data["source_url"]:
            card.source_url = data["source_url"]
        card.extra = {**(card.extra or {}), **data["extra"]}
        card.fetched_at = now
        card.status = Card.Status.STAGING
        card.save()
        for name in data["tags"]:
            slug = slugify(name.replace("ı", "i")) or "etiket"
            tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": name})
            card.tags.add(tag)
        for key, value in row["values"].items():
            defaults = {"number": Decimal(value["number"]), "year": None, "month": None, "day": None} \
                if "number" in value else {"number": None, **value}
            if data["source_url"]:
                defaults["source_url"] = data["source_url"]
            CardValue.objects.update_or_create(card=card, attribute=attributes[key], defaults=defaults)
        services.extend_schema(card)
        counts["created" if row["action"] == "create" else "updated"] += 1
    return counts
