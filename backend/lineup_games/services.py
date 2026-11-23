"""
Django side of a game: loads cards into engine objects, creates runs with a frozen deck (paid with energy), applies
moves under a row lock and builds the payloads (a card's value is only ever sent after it was played). The daily
puzzle is free and created by the first request of the day.
"""

import secrets
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

from billing import services as billing
from lineup_cards.models import Attribute, Card, CardValue

from .engine import daily, decks, energy, streak, timeline
from .engine.decks import DeckCard
from .engine.values import Value, sort_key
from .models import DailyPlay, DailyPuzzle, Energy, Move, Run
from .signals import run_finished

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


PRO = "pro"
PRO_FOREVER = datetime.max.replace(tzinfo=UTC)  # Pro without an end date


def pro_until(user) -> datetime | None:
    """End of the user's Pro (unlimited energy, ad-free continue, daily archive); None = not Pro."""
    ent = billing.entitlement(user, PRO)
    return None if ent is None else ent.expires_at or PRO_FOREVER


def unlimited_until(user, now: datetime) -> datetime | None:
    """End of the no-limit period: Pro, or new players' first days. None when limited."""
    grace = timedelta(days=settings.LINEUP_ENERGY_GRACE_DAYS)
    ends = [d for d in (pro_until(user),
                        user.date_joined + grace if energy.in_grace(user.date_joined, now, grace) else None) if d]
    return max(ends) if ends else None


def _seconds(until: datetime | None, now: datetime) -> int | None:
    return None if until is None else max(0, int((until - now).total_seconds()))


def energy_payload(user, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    rules = energy_rules()
    row = Energy.objects.filter(user=user).first()
    state = energy.settle(row.state(), now, rules) if row else energy.full(now, rules)
    unlimited = unlimited_until(user, now)
    return {
        "current": state.stored, "max": rules.max, "cost": ENERGY_COST,
        "unlimited": unlimited is not None,
        "unlimited_seconds": None if unlimited in (None, PRO_FOREVER) else _seconds(unlimited, now),
        "pro": pro_until(user) is not None,
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
    Run.objects.filter(user=user, mode=mode, status=Run.Status.PLAYING, is_challenge=False).update(
        status=Run.Status.ABANDONED, finished_at=now)
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
    if not playing:
        run_finished.send(sender=Run, run=run)
    return run, result


def new_challenge_run(user, source: Run) -> Run:
    """A free run on another run's frozen deck (challenge accepted): same mode, attribute, deck and rules."""
    run = Run(user=user, mode=source.mode, difficulty=source.difficulty, attribute=source.attribute,
              seed=source.seed, deck=list(source.deck), target=source.target, is_challenge=True)
    if source.mode == Run.Mode.STREAK:
        run.set_streak_state(streak.start(run.deck))
    else:
        run.set_timeline_state(timeline.start(run.deck, target=source.target))
    run.dealt_at = timezone.now()
    run.save()
    return run


def resume_run(run: Run) -> None:
    """One more life for a lost run (caller checked it can continue and holds the row lock)."""
    if run.mode == Run.Mode.STREAK:
        run.set_streak_state(streak.resume(run.streak_state()))
    else:
        run.set_timeline_state(timeline.resume(run.timeline_state()))
    run.dealt_at, run.finished_at = timezone.now(), None
    run.save()


@transaction.atomic
def continue_run(user, run_id) -> Run:
    """Pro: continue a lost run without an ad (everyone else goes through the rewarded ad)."""
    run = Run.objects.select_for_update().select_related("attribute").filter(user=user, pk=run_id).first()
    if run is None:
        raise NotFound("Tur bulunamadı.", code="run_not_found")
    if pro_until(user) is None:
        raise GameConflict("Reklamsız devam Pro'ya özel.", code="pro_required")
    state = run.streak_state() if run.mode == Run.Mode.STREAK else run.timeline_state()
    engine = streak if run.mode == Run.Mode.STREAK else timeline
    if not engine.can_continue(state):
        raise GameConflict("Bu tur devam ettirilemez.", code="cannot_continue")
    resume_run(run)
    return run


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
        data["sort"] = sort_key(_value(value))  # display order for the value axes, never used to judge
    return data


def best_streak(user_id) -> int:
    """Records count normal runs only (challenge runs are free)."""
    runs = Run.objects.filter(user_id=user_id, mode=Run.Mode.STREAK, is_challenge=False)
    return runs.aggregate(best=Max("score"))["best"] or 0


def run_payload(run: Run) -> dict:
    a = run.attribute
    data = {
        "id": str(run.pk), "mode": run.mode, "difficulty": run.difficulty, "status": run.status,
        "lives": run.lives, "score": run.score, "continues_used": run.continues_used,
        "is_challenge": run.is_challenge,
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
            "can_continue": timeline.can_continue(state),
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


# ---------------------------------------------------------------- daily puzzle
DAILY_TZ = ZoneInfo("Europe/Istanbul")
SHARE_MARKS = {daily.RIGHT: "🟩", daily.NEAR: "🟨", daily.WRONG: "🟥"}


def daily_reset() -> time:
    """Istanbul time a new puzzle starts (LINEUP_DAILY_RESET, "07:30")."""
    return time.fromisoformat(settings.LINEUP_DAILY_RESET)


def daily_date(now: datetime | None = None) -> date:
    """The puzzle day: before the reset time it is still the previous day's puzzle."""
    reset = daily_reset()
    local = timezone.localtime(now or timezone.now(), DAILY_TZ)
    return (local - timedelta(hours=reset.hour, minutes=reset.minute)).date()


def next_daily_seconds(now: datetime | None = None) -> int:
    now = now or timezone.now()
    nxt = datetime.combine(daily_date(now) + timedelta(days=1), daily_reset(), tzinfo=DAILY_TZ)
    return _seconds(nxt, now)


def daily_puzzle(day: date | None = None) -> DailyPuzzle:
    """The day's puzzle; the first request of the day creates it (random playable attribute, frozen deck)."""
    day = day or daily_date()
    puzzle = DailyPuzzle.objects.select_related("attribute").filter(date=day).first()
    if puzzle:
        return puzzle
    attribute = playable_attribute(None, daily.SIZE)
    seed = secrets.token_hex(8)
    deck = decks.daily_deck(seed, candidates(attribute), daily.SIZE,
                            is_date=attribute.value_type == Attribute.ValueType.DATE)
    if len(deck) < 2:
        raise GameConflict("Bulmaca için yeterli kart yok.", code="not_enough_cards")
    try:
        with transaction.atomic():
            number = (DailyPuzzle.objects.aggregate(n=Max("number"))["n"] or 0) + 1
            return DailyPuzzle.objects.create(date=day, number=number, attribute=attribute, seed=seed, deck=deck)
    except IntegrityError:  # a parallel request created it first
        return DailyPuzzle.objects.select_related("attribute").get(date=day)


ARCHIVE_SIZE = 60


def daily_by_number(user, number: int | None) -> DailyPuzzle:
    """Today's puzzle, or a past one for Pro (archive). A future / unknown number is not found."""
    today = daily_puzzle()
    if number is None or number == today.number:
        return today
    puzzle = DailyPuzzle.objects.select_related("attribute").filter(number=number, date__lt=today.date).first()
    if puzzle is None:
        raise NotFound("Bulmaca bulunamadı.", code="daily_not_found")
    if pro_until(user) is None:
        raise GameConflict("Geçmiş bulmacalar Pro'ya özel.", code="pro_required")
    return puzzle


def daily_archive(user) -> list[dict]:
    """Pro: past puzzles (newest first) with how far the user got."""
    if pro_until(user) is None:
        raise GameConflict("Geçmiş bulmacalar Pro'ya özel.", code="pro_required")
    today = daily_puzzle()
    puzzles = list(DailyPuzzle.objects.filter(date__lt=today.date).select_related("attribute")[:ARCHIVE_SIZE])
    plays = {p.puzzle_id: p for p in DailyPlay.objects.filter(user=user, puzzle__in=puzzles)}
    rows = []
    for puzzle in puzzles:
        play = plays.get(puzzle.pk)
        rows.append({"number": puzzle.number, "date": puzzle.date.isoformat(), "attribute": puzzle.attribute.name,
                     "status": play.status if play and play.attempts else "new",
                     "solved_in": play.solved_in if play else None})
    return rows


@transaction.atomic
def submit_daily(user, number: int, order: list[str]):
    """
    One attempt (free). Today's puzzle for everyone; a past one only for Pro (archive). An old number without Pro is
    "expired" (the day changed while playing). Returns (play, engine result).
    """
    today = daily_puzzle()
    if number == today.number:
        puzzle = today
    elif pro_until(user) is not None:
        puzzle = daily_by_number(user, number)
    else:
        raise GameConflict("Bu bulmacanın günü geçti; yeni bulmaca hazır.", code="daily_expired")
    play, created = DailyPlay.objects.select_for_update().get_or_create(
        user=user, puzzle=puzzle, defaults={"late": puzzle.pk != today.pk})
    if play.status != DailyPlay.Status.PLAYING:
        raise GameConflict("Bugünkü bulmacayı bitirdin.", code="daily_over")
    try:
        result = daily.submit(play.state(), order, _values(puzzle.attribute, puzzle.deck))
    except ValueError:
        raise GameConflict("Geçersiz sıralama.", code="invalid_order") from None
    play.attempts.append({"order": list(order), "marks": list(result.marks)})
    play.status = result.state.status
    play.finished_at = None if play.status == DailyPlay.Status.PLAYING else timezone.now()
    play.save()
    return play, result


def share_text(puzzle: DailyPuzzle, play: DailyPlay) -> str:
    """Wordle-style result: one row of squares per attempt, no card names (no spoilers)."""
    rows = ["".join(SHARE_MARKS[m] for m in a["marks"]) for a in play.attempts]
    end = f"{play.solved_in}. deneme" if play.solved_in else "çözülemedi"
    rows[-1] = f"{rows[-1]} – {end}"
    return "\n".join([f"Line Up · Günlük #{puzzle.number} ({puzzle.attribute.name})", *rows])


def daily_payload(user, puzzle: DailyPuzzle | None = None, play: DailyPlay | None = None) -> dict:
    """Cards in the current order (last attempt, else as shown); values, solution and share text once finished."""
    puzzle = puzzle or daily_puzzle()
    play = play or DailyPlay.objects.filter(user=user, puzzle=puzzle).first()
    attempts = play.attempts if play else []
    state = play.status if play and attempts else "new"
    finished = state in (DailyPlay.Status.WON, DailyPlay.Status.LOST)
    a = puzzle.attribute
    cards = _cards(puzzle.deck, a)
    order = attempts[-1]["order"] if attempts else puzzle.deck
    data = {
        "number": puzzle.number, "date": puzzle.date.isoformat(), "status": state,
        "archived": puzzle.date < daily_date(),
        "max_attempts": daily.ATTEMPTS, "attempts_left": daily.ATTEMPTS - len(attempts),
        "solved_in": play.solved_in if play else None,
        "attribute": {"key": a.key, "name": a.name, "unit": a.unit,
                      "lower_label": a.lower_label, "higher_label": a.higher_label},
        "cards": [card_payload(*cards[c]) if finished else card_payload(cards[c][0]) for c in order if c in cards],
        "attempts": attempts,
        "next_in_seconds": next_daily_seconds(),
    }
    if finished:
        values = {c: _value(cv) for c, (_, cv) in cards.items() if cv is not None}
        data["solution"] = [card_payload(*cards[c]) for c in daily.solution(list(values), values)]
        data["share"] = share_text(puzzle, play)
    return data


def daily_home(user) -> dict | None:
    """Home tile: today's number and how far the user got; None when no puzzle can be made."""
    try:
        puzzle = daily_puzzle()
    except GameConflict:
        return None
    play = DailyPlay.objects.filter(user=user, puzzle=puzzle).first()
    return {
        "number": puzzle.number,
        "status": play.status if play and play.attempts else "new",
        "attempts_used": len(play.attempts) if play else 0,
        "max_attempts": daily.ATTEMPTS,
        "solved_in": play.solved_in if play else None,
        "streak": daily_streaks(user, puzzle, play)[0],
        "next_in_seconds": next_daily_seconds(),
    }


def daily_streaks(user, puzzle: DailyPuzzle, play: DailyPlay | None) -> tuple[int, int]:
    """(current, best) consecutive solved puzzles; today's open puzzle does not break the run yet."""
    won = set(DailyPlay.objects.filter(user=user, status=DailyPlay.Status.WON, late=False)
              .values_list("puzzle__number", flat=True))
    lost = bool(play and play.status == DailyPlay.Status.LOST)
    return daily.streaks(won, puzzle.number, current_lost=lost)


# ---------------------------------------------------------------- profile
def profile_payload(user) -> dict:
    """Stats per mode. Played = finished runs (abandoned ones and the run being played do not count)."""
    done = [Run.Status.WON, Run.Status.LOST, Run.Status.FINISHED]
    runs = Run.objects.filter(user=user, status__in=done, is_challenge=False).aggregate(
        timeline_played=Count("id", filter=Q(mode=Run.Mode.TIMELINE)),
        timeline_wins=Count("id", filter=Q(mode=Run.Mode.TIMELINE, status=Run.Status.WON)),
        timeline_best=Max("score", filter=Q(mode=Run.Mode.TIMELINE)),
        streak_played=Count("id", filter=Q(mode=Run.Mode.STREAK)),
    )
    plays = DailyPlay.objects.filter(user=user).exclude(status=DailyPlay.Status.PLAYING)
    distribution = {str(n): 0 for n in range(1, daily.ATTEMPTS + 1)} | {"fail": 0}
    for play in plays.only("status", "attempts"):
        distribution[str(play.solved_in) if play.solved_in else "fail"] += 1
    try:
        puzzle = daily_puzzle()
        current, best = daily_streaks(user, puzzle, DailyPlay.objects.filter(user=user, puzzle=puzzle).first())
    except GameConflict:
        current, best = 0, 0
    played = sum(distribution.values())
    return {
        "timeline": {"played": runs["timeline_played"], "wins": runs["timeline_wins"],
                     "best_score": runs["timeline_best"] or 0},
        "streak": {"played": runs["streak_played"], "best": best_streak(user.pk)},
        "daily": {"played": played, "solved": played - distribution["fail"], "current_streak": current,
                  "best_streak": best, "distribution": distribution},
    }


def home_payload(user) -> dict:
    runs = Run.objects.filter(user=user, is_challenge=False)
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
        "daily": daily_home(user),
        "pro": pro_payload(user),
        "ads_left_today": billing.ads_left_today(user),
    }


def pro_payload(user) -> dict:
    until = pro_until(user)
    return {"active": until is not None,
            "expires_at": None if until in (None, PRO_FOREVER) else until.isoformat()}
