"""Card review: what blocks approval, what only deserves a look, and status changes."""

from .models import Card

LOW_POPULARITY = 20

# everything approval_problems / review_warnings read, for lists (no query per card)
REVIEW_PREFETCH = ["values__attribute", "card_type__schema_attributes__attribute", "card_type__fields"]


def approval_problems(card: Card) -> list[str]:
    """Blocking: an approved card must be playable and complete for its type."""
    problems = []
    if not card.title.strip():
        problems.append("Başlık boş.")
    if card.title_lang != "tr":
        problems.append(f"Türkçe başlık gerekli (dil: {card.title_lang}).")
    have = {v.attribute_id for v in card.values.all()}
    if not have:
        problems.append("Hiç değer yok.")
    missing = [entry.attribute.name for entry in card.card_type.schema_attributes.all()
               if entry.is_required and entry.attribute_id not in have]
    if missing:
        problems.append(f"Eksik değer: {', '.join(missing)}.")
    extra = card.extra or {}
    missing_fields = [f.label for f in card.card_type.fields.all()
                      if f.is_required and not str(extra.get(f.key, "")).strip()]
    if missing_fields:
        problems.append(f"Eksik ek alan: {', '.join(missing_fields)}.")
    return problems


def review_warnings(card: Card) -> list[str]:
    """Not blocking, shown to the reviewer."""
    warnings = []
    if card.popularity < LOW_POPULARITY:
        warnings.append(f"Tanınırlık çok düşük ({card.popularity}).")
    if not card.source_url and not card.is_demo and not any(v.source_url for v in card.values.all()):
        warnings.append("Kaynak yok.")
    if card.is_demo:
        warnings.append("Demo kart (uydurma veri).")
    return warnings


def set_status(cards, status: str) -> tuple[int, list[tuple[Card, list[str]]]]:
    """Change the status of cards; approval skips cards with problems. Returns (changed, skipped with reasons)."""
    changed, skipped = 0, []
    for card in cards:
        if status == Card.Status.APPROVED:
            problems = approval_problems(card)
            if problems:
                skipped.append((card, problems))
                continue
        if card.status != status:
            card.status = status
            card.save(update_fields=["status", "updated_at"])
            changed += 1
    return changed, skipped
