"""Seeded deck generation: the same seed and the same candidate pool always give the same deck."""

import random
from dataclasses import dataclass, field

from .values import Value, gap


@dataclass(frozen=True)
class DeckCard:
    """What the generator needs to know about a card for one compared attribute."""

    id: str
    value: Value
    popularity: int = 50
    type_key: str = ""
    tags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class DeckParams:
    """
    Difficulty knobs. min_gap: years between any two dates, or relative difference for numbers (0.2 = 20%).
    When the pool is too small for the gap, it is halved until the deck is full (down to 0).
    """

    size: int
    min_popularity: int = 0
    min_gap: float = 0
    type_keys: frozenset[str] = field(default_factory=frozenset)  # empty = every card type (category mix)
    tags: frozenset[str] = field(default_factory=frozenset)  # empty = no tag filter


DIFFICULTY = {
    # name: (min popularity, date gap in years, number gap as a fraction)
    "easy": (60, 15, 0.3),
    "normal": (40, 4, 0.12),
    "hard": (0, 0, 0.0),
}


def params_for(difficulty: str, size: int, is_date: bool, **filters) -> DeckParams:
    popularity, date_gap, number_gap = DIFFICULTY[difficulty]
    return DeckParams(size=size, min_popularity=popularity, min_gap=date_gap if is_date else number_gap, **filters)


def eligible(candidates: list[DeckCard], params: DeckParams) -> list[DeckCard]:
    return [c for c in candidates
            if c.popularity >= params.min_popularity
            and (not params.type_keys or c.type_key in params.type_keys)
            and (not params.tags or c.tags & params.tags)]


def generate(seed: str, candidates: list[DeckCard], params: DeckParams) -> list[str]:
    """Card ids in play order. Shorter than params.size only when the pool is too small."""
    rng = random.Random(seed)
    pool = sorted(eligible(candidates, params), key=lambda c: c.id)  # order-independent of the caller
    rng.shuffle(pool)
    min_gap = params.min_gap
    while True:
        picked: list[DeckCard] = []
        for card in pool:
            if all(gap(card.value, other.value) >= min_gap for other in picked):
                picked.append(card)
                if len(picked) == params.size:
                    return [c.id for c in picked]
        if min_gap <= 0:
            return [c.id for c in picked]
        # relax: halve three times (15 -> 7.5 -> 3.75 -> 1.875 years), then no gap at all
        min_gap = min_gap / 2 if min_gap / 2 >= params.min_gap / 8 else 0


# Streak: famous cards first and wide gaps at the start; the gap to the previous card shrinks as the streak grows.
STREAK_STAGES = (
    # (last deck position of the stage, difficulty whose popularity tier / gap applies)
    (5, "easy"),
    (15, "normal"),
)


def _streak_stage(position: int) -> str:
    return next((name for last, name in STREAK_STAGES if position <= last), "hard")


def streak_deck(seed: str, candidates: list[DeckCard], size: int, is_date: bool) -> list[str]:
    """
    Card ids in play order. Pool order: seeded shuffle, then popularity tier (easy, normal, rest) so famous cards come
    first. Each next card is the first one in that order far enough from the previous card for its stage; when none
    is, the farthest one is taken.
    """
    rng = random.Random(seed)
    pool = sorted(candidates, key=lambda c: c.id)
    rng.shuffle(pool)
    tiers = [DIFFICULTY["easy"][0], DIFFICULTY["normal"][0]]
    pool.sort(key=lambda c: next((i for i, t in enumerate(tiers) if c.popularity >= t), len(tiers)))
    if not pool:
        return []
    deck = [pool.pop(0)]
    while pool and len(deck) < size:
        _, date_gap, number_gap = DIFFICULTY[_streak_stage(len(deck))]
        needed = date_gap if is_date else number_gap
        previous = deck[-1].value
        index = next((i for i, c in enumerate(pool) if gap(c.value, previous) >= needed), None)
        if index is None:
            index = max(range(len(pool)), key=lambda i: gap(pool[i].value, previous))
        deck.append(pool.pop(index))
    return [c.id for c in deck]
