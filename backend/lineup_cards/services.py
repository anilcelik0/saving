"""Card review: what blocks approval, what only deserves a look, and status changes."""

import uuid

from .models import Attribute, Card, CardTypeAttribute

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


def extend_schema(card: Card) -> list[Attribute]:
    """Attributes the card has values for but its type lacks: added to the type as optional. Returns them."""
    known = set(card.card_type.schema_attributes.values_list("attribute_id", flat=True))
    added = []
    for value in card.values.select_related("attribute"):
        if value.attribute_id not in known:
            CardTypeAttribute.objects.create(card_type=card.card_type, attribute=value.attribute, is_required=False)
            known.add(value.attribute_id)
            added.append(value.attribute)
    return added


def card_snapshot(user, object_id: str):
    """support.registry provider for "lineup.card": cards are shared content, any Line Up user may report one."""
    if user.app_id is None or user.app.slug != "lineup":
        return None
    try:
        card = Card.objects.select_related("card_type").prefetch_related("values__attribute").get(
            pk=uuid.UUID(str(object_id)))
    except (ValueError, Card.DoesNotExist):
        return None
    return {"title": str(card), "type": card.card_type.name, "status": card.status, "is_demo": card.is_demo,
            "external_key": card.external_key, "values": [str(v) for v in card.values.all()]}
