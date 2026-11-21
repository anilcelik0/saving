"""
Django side of a game: loads cards into engine objects, creates runs with a frozen deck (paid with energy), applies
moves under a row lock and builds the payloads (a card's value is only ever sent after it was played).
"""

import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

from lineup_cards.models import Attribute, Card, CardValue

from .engine import decks, energy, streak, timeline
from .engine.decks import DeckCard
from .engine.values import Value
from .models import Energy, Move, Run

DIFFICULTIES = {"easy": "Kolay", "normal": "Normal", "hard": "Zor"}
ENERGY_COST = 1  # per Timeline / Streak start; the daily puzzle and accepted challenges are free
STREAK_HISTORY = 8  # revealed cards shown under the open card


class GameConflict(APIException):
    status_code = 409
    default_detail = "Bu işlem şu an yapılamaz."
    default_code = "game_conflict"


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


def _values(attribute: Attribute, ids: list[str]) -> dict[str, Value]:
    values = {str(cv.card_id): _value(cv) for cv in CardValue.objects.filter(attribute=attribute, card_id__in=ids)}
    if len(values) != len(set(ids)):  # a card was deleted or lost its value after the deck was frozen
        raise GameConflict("Bu kart artık oyunda değil; lütfen yeni tur başlatın.", code="card_missing")
    return values


# ---------------------------------------------------------------- energy
def energy_rules() -> energy.EnergyRules:
    return energy.EnergyRules(max=settings.LINEUP_ENERGY_MAX,
                              refill=timedelta(minutes=settings.LINEUP_ENERGY_REFILL_MINUTES))


def unlimited_until(user, now: datetime) -> datetime | None:
    """End of the no-limit period (new players' first days; Pro joins here in Phase 5), None when limited."""
    grace = timedelta(days=settings.LINEUP_ENERGY_GRACE_DAYS)
    return user.date_joined + grace if energy.in_grace(user.date_joined, now, grace) else None


def _seconds(until: datetime | None, now: datetime) -> int | None:
    return None if until is None else max(0, int((until - now).total_seconds()))


def energy_payload(user, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    rules = energy_rules()
    row = Energy.objects.filter(user=user).first()
    state = energy.settle(row.state(), now, rules) if row else energy.full(now, rules)
    return {
        "current": state.stored, "max": rules.max, "cost": ENERGY_COST,
        "unlimited": unlimited_until(user, now) is not None,
        "unlimited_seconds": _seconds(unlimited_until(user, now), now),
        "next_in_seconds": _seconds(energy.next_at(state, rules), now),
        "full_in_seconds": _seconds(energy.full_at(state, rules), now),
    }


def _spend_energy(user, now: datetime) -> None:
    """Inside the start transaction: the row lock serializes parallel starts."""
    if unlimited_until(user, now):
        return
    rules = energy_rules()
    row, _ = Energy.objects.select_for_update().get_or_create(user=user, defaults={"stored": rules.max, "since": now})
    try:
        row.set_state(energy.spend(row.state(), now, rules, ENERGY_COST))
    except energy.NotEnoughEnergy:
        raise GameConflict("Enerjin bitti.", code="no_energy") from None
    row.save()


# ---------------------------------------------------------------- runs
def _new_timeline(user, difficulty: str, attribute_key: str | None) -> Run:
    size = timeline.deck_size()
    attribute = playable_attribute(attribute_key, size)
    seed = secrets.token_hex(8)
    params = decks.params_for(difficulty, size, is_date=attribute.value_type == Attribute.ValueType.DATE)
    deck = decks.generate(seed, candidates(attribute), params)
    if len(deck) < 2:
        raise GameConflict("Bu zorlukta oynamak için yeterli kart yok.", code="not_enough_cards")
    run = Run(user=user, mode=Run.Mode.TIMELINE, difficulty=difficulty, attribute=attribute, seed=seed, deck=deck)
    run.set_timeline_state(timeline.start(deck))
    return run


def _new_streak(user, attribute_key: str | None) -> Run:
    attribute = playable_attribute(attribute_key, timeline.deck_size())
    seed = secrets.token_hex(8)
    deck = decks.streak_deck(seed, candidates(attribute), streak.DECK_SIZE,
                             is_date=attribute.value_type == Attribute.ValueType.DATE)
    if len(deck) < 2:
        raise GameConflict("Oynamak için yeterli kart yok.", code="not_enough_cards")
    run = Run(user=user, mode=Run.Mode.STREAK, difficulty="", attribute=attribute, seed=seed, deck=deck, target=0)
    run.set_streak_state(streak.start(deck))
    return run


@transaction.atomic
def start_run(user, mode: str, difficulty: str = "normal", attribute_key: str | None = None) -> Run:
    """New run for one energy point; a run of the same mode still being played is abandoned."""
    if mode == Run.Mode.TIMELINE:
        if difficulty not in DIFFICULTIES:
            raise GameConflict("Geçersiz zorluk.", code="unknown_difficulty")
        run = _new_timeline(user, difficulty, attribute_key)
    elif mode == Run.Mode.STREAK:
        run = _new_streak(user, attribute_key)
    else:
        raise GameConflict("Geçersiz mod.", code="unknown_mode")
    now = timezone.now()
    _spend_energy(user, now)
    Run.objects.filter(user=user, mode=mode, status=Run.Status.PLAYING).update(status=Run.Status.ABANDONED,
                                                                               finished_at=now)
    run.dealt_at = now
    run.save()
    return run


MAX_ELAPSED_MS = 2**31 - 1  # Move.elapsed_ms column limit (~24 days); a run can be resumed much later


def _elapsed_ms(dealt_at, now) -> int:
    return min(MAX_ELAPSED_MS, int((now - dealt_at).total_seconds() * 1000)) if dealt_at else 0


@transaction.atomic
def play_move(user, run_id, slot: int | None = None, guess: str | None = None):
    """Timeline takes `slot`, Streak takes `guess`. Returns (run, engine result)."""
    run = Run.objects.select_for_update().select_related("attribute").filter(user=user, pk=run_id).first()
    if run is None:
        raise NotFound("Tur bulunamadı.", code="run_not_found")
    if run.status != Run.Status.PLAYING:
        raise GameConflict("Bu tur bitti.", code="run_over")
    now = timezone.now()
    move = Move(run=run, number=run.moves.count() + 1, elapsed_ms=_elapsed_ms(run.dealt_at, now))
    if run.mode == Run.Mode.STREAK:
        if guess not in streak.GUESSES:
            raise GameConflict("Geçersiz tahmin.", code="invalid_guess")
        state = run.streak_state()
        result = streak.guess(state, guess, _values(run.attribute, [state.open, state.current]))
        move.guess = guess
        run.set_streak_state(result.state)
    else:
        if slot is None:
            raise GameConflict("Geçersiz yer.", code="invalid_slot")
        state = run.timeline_state()
        try:
            result = timeline.place(state, slot, _values(run.attribute, [*state.line, state.current]))
        except ValueError:
            raise GameConflict("Geçersiz yer.", code="invalid_slot") from None
        move.slot = slot
        run.set_timeline_state(result.state)
    move.card_id, move.correct = result.card_id, result.correct
    move.save()
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
    """Public card. `value` only for cards already revealed (on the line, open, or just played)."""
    labels = {f.key: f.label for f in card.card_type.fields.all()}
    data = {
        "id": str(card.pk), "title": card.title, "subtitle": card.subtitle, "emoji": card.card_type.emoji,
        "type": card.card_type.name,
        "details": [f"{labels[k]}: {v}" for k, v in (card.extra or {}).items() if k in labels],
    }
    if value is not None:
        data["value"] = value.display()
    return data


def best_streak(user_id) -> int:
    return Run.objects.filter(user_id=user_id, mode=Run.Mode.STREAK).aggregate(best=Max("score"))["best"] or 0


def run_payload(run: Run) -> dict:
    a = run.attribute
    data = {
        "id": str(run.pk), "mode": run.mode, "difficulty": run.difficulty, "status": run.status,
        "lives": run.lives, "score": run.score,
        "attribute": {"key": a.key, "name": a.name, "unit": a.unit,
                      "lower_label": a.lower_label, "higher_label": a.higher_label},
        "created_at": run.created_at.isoformat(),
    }
    if run.mode == Run.Mode.STREAK:
        state = run.streak_state()
        current = state.current
        history = list(reversed(run.deck[max(0, state.next_index - 1 - STREAK_HISTORY):state.next_index - 1]))
        cards = _cards([state.open, *history, *([current] if current else [])], a)
        data.update({
            "open": card_payload(*cards[state.open]) if state.open in cards else None,
            "current": card_payload(cards[current][0]) if current and current in cards else None,
            "history": [card_payload(*cards[c]) for c in history if c in cards],
            "can_continue": streak.can_continue(state),
            "best": best_streak(run.user_id),
        })
    else:
        state = run.timeline_state()
        current = state.current
        cards = _cards([*run.line, *([current] if current else [])], a)
        data.update({
            "target": run.target,
            "line": [card_payload(*cards[c]) for c in run.line if c in cards],
            "current": card_payload(cards[current][0]) if current and current in cards else None,
        })
    return data


def move_payload(run: Run, result, slot: int | None = None, guess: str | None = None) -> dict:
    card, value = _cards([result.card_id], run.attribute)[result.card_id]
    if run.mode == Run.Mode.STREAK:
        outcome = {"correct": result.correct, "guess": guess, "relation": result.relation}
    else:
        outcome = {"correct": result.correct, "slot": slot, "valid_slots": list(result.valid_slots)}
    return {"result": {**outcome, "card": card_payload(card, value)}, "run": run_payload(run)}


def home_payload(user) -> dict:
    runs = Run.objects.filter(user=user)
    playing = {mode: None for mode in Run.Mode.values}
    for run in runs.filter(status=Run.Status.PLAYING).order_by("created_at"):
        playing[run.mode] = {"id": str(run.pk), "score": run.score}
    stats = runs.aggregate(best_streak=Max("score", filter=Q(mode=Run.Mode.STREAK)),
                           timeline_wins=Count("id", filter=Q(mode=Run.Mode.TIMELINE, status=Run.Status.WON)))
    return {
        "energy": energy_payload(user),
        "playing": playing,
        "best_streak": stats["best_streak"] or 0,
        "timeline_wins": stats["timeline_wins"],
    }
