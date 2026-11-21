"""
Django side of a game: loads cards into engine objects, creates runs with a frozen deck, applies moves under a row
lock and builds the payloads (a card's value is only ever sent after it was played).
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

from lineup_cards.models import Attribute, Card, CardValue

from .engine import decks, timeline
from .engine.decks import DeckCard
from .engine.values import Value
from .models import Move, Run

DIFFICULTIES = {"easy": "Kolay", "normal": "Normal", "hard": "Zor"}


class GameConflict(APIException):
    status_code = 409
    default_detail = "Bu işlem şu an yapılamaz."
    default_code = "game_conflict"


def move_seconds() -> int:
    return settings.LINEUP_MOVE_SECONDS


# ---------------------------------------------------------------- cards -> engine
def _value(cv: CardValue) -> Value:
    return Value(number=cv.number, year=cv.year, month=cv.month, day=cv.day)


def candidates(attribute: Attribute) -> list[DeckCard]:
    """Approved cards that have a value for the attribute."""
    rows = (CardValue.objects.filter(attribute=attribute, card__status=Card.Status.APPROVED)
            .select_related("card__card_type").prefetch_related("card__tags"))
    return [DeckCard(id=str(cv.card_id), value=_value(cv), popularity=cv.card.popularity,
                     type_key=cv.card.card_type.key, tags=frozenset(t.slug for t in cv.card.tags.all()))
            for cv in rows]


def playable_attribute(key: str | None, needed: int) -> Attribute:
    """The requested attribute, else a random active one with enough approved cards (else the richest one)."""
    attributes = Attribute.objects.filter(is_active=True).annotate(
        cards=Count("card_values", filter=Q(card_values__card__status=Card.Status.APPROVED)))
    if key:
        attribute = attributes.filter(key=key).first()
        if attribute is None:
            raise GameConflict("Böyle bir nitelik yok.", code="unknown_attribute")
        return attribute
    rich = [a for a in attributes if a.cards >= needed]
    if rich:
        return secrets.choice(rich)
    best = max(attributes, key=lambda a: a.cards, default=None)
    if best is None or best.cards < 2:
        raise GameConflict("Oynamak için yeterli kart yok.", code="not_enough_cards")
    return best


# ---------------------------------------------------------------- runs
def start_timeline(user, difficulty: str = "normal", attribute_key: str | None = None) -> Run:
    if difficulty not in DIFFICULTIES:
        raise GameConflict("Geçersiz zorluk.", code="unknown_difficulty")
    size = timeline.deck_size()
    attribute = playable_attribute(attribute_key, size)
    seed = secrets.token_hex(8)
    params = decks.params_for(difficulty, size, is_date=attribute.value_type == Attribute.ValueType.DATE)
    deck = decks.generate(seed, candidates(attribute), params)
    if len(deck) < 2:
        raise GameConflict("Bu zorlukta oynamak için yeterli kart yok.", code="not_enough_cards")
    state = timeline.start(deck)
    run = Run(user=user, mode=Run.Mode.TIMELINE, difficulty=difficulty, attribute=attribute, seed=seed,
              deck=list(state.deck), dealt_at=timezone.now())
    run.set_timeline_state(state)
    run.save()
    return run


@transaction.atomic
def play_move(user, run_id, slot: int | None) -> tuple[Run, timeline.PlaceResult]:
    run = Run.objects.select_for_update().select_related("attribute").filter(user=user, pk=run_id).first()
    if run is None:
        raise NotFound("Tur bulunamadı.", code="run_not_found")
    if run.status != Run.Status.PLAYING:
        raise GameConflict("Bu tur bitti.", code="run_over")
    now = timezone.now()
    state = run.timeline_state()
    ids = [*state.line, state.current]
    values = {str(cv.card_id): _value(cv)
              for cv in CardValue.objects.filter(attribute=run.attribute, card_id__in=ids)}
    if len(values) != len(ids):  # a card was deleted or lost its value after the deck was frozen
        raise GameConflict("Bu kart artık oyunda değil; lütfen yeni tur başlatın.", code="card_missing")
    timed_out = run.dealt_at is None or timeline.is_timed_out(run.dealt_at, now, move_seconds(),
                                                               settings.LINEUP_MOVE_GRACE_SECONDS)
    try:
        result = timeline.place(state, slot, values, timed_out=timed_out)
    except ValueError:
        raise GameConflict("Geçersiz yer.", code="invalid_slot") from None
    Move.objects.create(run=run, number=run.moves.count() + 1, card_id=result.card_id, slot=slot,
                        correct=result.correct, timed_out=result.timed_out,
                        elapsed_ms=int((now - run.dealt_at).total_seconds() * 1000) if run.dealt_at else 0)
    run.set_timeline_state(result.state)
    playing = run.status == Run.Status.PLAYING
    run.dealt_at = now if playing else None
    run.finished_at = None if playing else now
    run.save()
    return run, result


# ---------------------------------------------------------------- payloads
def _cards(ids, attribute) -> dict[str, tuple[Card, CardValue | None]]:
    cards = Card.objects.filter(pk__in=ids).select_related("card_type").prefetch_related("card_type__fields")
    found = {str(c.pk): c for c in cards}
    vals = {str(v.card_id): v for v in CardValue.objects.filter(card_id__in=ids, attribute=attribute)
            .select_related("attribute")}
    return {i: (found[i], vals.get(i)) for i in ids if i in found}


def card_payload(card: Card, value: CardValue | None = None) -> dict:
    """Public card. `value` only for cards already on the line or just played."""
    labels = {f.key: f.label for f in card.card_type.fields.all()}
    data = {
        "id": str(card.pk), "title": card.title, "subtitle": card.subtitle, "emoji": card.card_type.emoji,
        "type": card.card_type.name,
        "details": [f"{labels[k]}: {v}" for k, v in (card.extra or {}).items() if k in labels],
    }
    if value is not None:
        data["value"] = value.display()
    return data


def run_payload(run: Run) -> dict:
    state = run.timeline_state()
    current = state.current
    cards = _cards([*run.line, *([current] if current else [])], run.attribute)
    now = timezone.now()
    remaining_ms = None
    if current and run.dealt_at:
        deadline = run.dealt_at + timedelta(seconds=move_seconds())
        remaining_ms = max(0, int((deadline - now).total_seconds() * 1000))
    a = run.attribute
    return {
        "id": str(run.pk), "mode": run.mode, "difficulty": run.difficulty, "status": run.status,
        "lives": run.lives, "score": run.score, "target": run.target,
        "attribute": {"key": a.key, "name": a.name, "unit": a.unit,
                      "lower_label": a.lower_label, "higher_label": a.higher_label},
        "line": [card_payload(*cards[c]) for c in run.line if c in cards],
        "current": card_payload(cards[current][0]) if current and current in cards else None,
        "move_seconds": move_seconds(), "remaining_ms": remaining_ms,
        "created_at": run.created_at.isoformat(),
    }


def move_payload(run: Run, result: timeline.PlaceResult, slot: int | None) -> dict:
    card, value = _cards([result.card_id], run.attribute)[result.card_id]
    return {
        "result": {"correct": result.correct, "timed_out": result.timed_out, "slot": slot,
                   "valid_slots": list(result.valid_slots), "card": card_payload(card, value)},
        "run": run_payload(run),
    }
