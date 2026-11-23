"""
Daily puzzle: everyone gets the same cards for the day and puts them in order (low to high). Each attempt marks
every position: right place, one place off, or further. Solved when every position is right; at most ATTEMPTS tries.
"""

from dataclasses import dataclass, replace
from functools import cmp_to_key

from .status import LOST, PLAYING, WON
from .values import Value, compare

SIZE = 6
ATTEMPTS = 5

RIGHT = "right"  # 🟩
NEAR = "near"  # 🟨 one place off
WRONG = "wrong"  # 🟥


@dataclass(frozen=True)
class DailyState:
    deck: tuple[str, ...]  # shown order
    attempts: tuple[tuple[str, ...], ...] = ()
    max_attempts: int = ATTEMPTS
    status: str = PLAYING

    @property
    def attempts_left(self) -> int:
        return self.max_attempts - len(self.attempts)

    @property
    def solved_in(self) -> int | None:
        """Attempt number that solved it."""
        return len(self.attempts) if self.status == WON else None


@dataclass(frozen=True)
class AttemptResult:
    state: DailyState
    marks: tuple[str, ...]
    solved: bool


def start(deck: list[str], max_attempts: int = ATTEMPTS) -> DailyState:
    if len(deck) < 2:
        raise ValueError("A puzzle needs at least two cards.")
    return DailyState(deck=tuple(deck), max_attempts=max_attempts)


def rank_range(card_id: str, values: dict[str, Value]) -> tuple[int, int]:
    """Positions (0-based) the card may take in a correct order; ties widen the range."""
    value = values[card_id]
    others = [v for c, v in values.items() if c != card_id]
    below = sum(1 for v in others if compare(v, value) < 0)
    above = sum(1 for v in others if compare(v, value) > 0)
    return below, len(values) - 1 - above


def marks(order: list[str] | tuple[str, ...], values: dict[str, Value]) -> tuple[str, ...]:
    """Per position: RIGHT inside the card's rank range, NEAR one place off it, else WRONG."""
    result = []
    for position, card_id in enumerate(order):
        low, high = rank_range(card_id, values)
        distance = max(low - position, position - high, 0)
        result.append(RIGHT if distance == 0 else NEAR if distance == 1 else WRONG)
    return tuple(result)


def solution(deck: list[str] | tuple[str, ...], values: dict[str, Value]) -> list[str]:
    """One correct order (tied cards keep their shown order)."""
    return sorted(deck, key=cmp_to_key(lambda a, b: compare(values[a], values[b])))


def submit(state: DailyState, order: list[str], values: dict[str, Value]) -> AttemptResult:
    """One attempt. `order` must hold exactly the puzzle's cards; `values` must hold all of them."""
    if state.status != PLAYING:
        raise ValueError("The puzzle is over.")
    if len(order) != len(state.deck) or set(order) != set(state.deck):
        raise ValueError("The order must hold exactly the puzzle's cards.")
    result = marks(order, {c: values[c] for c in state.deck})
    solved = all(m == RIGHT for m in result)
    attempts = state.attempts + (tuple(order),)
    status = WON if solved else LOST if len(attempts) >= state.max_attempts else PLAYING
    return AttemptResult(state=replace(state, attempts=attempts, status=status), marks=result, solved=solved)


def streaks(won: set[int], current: int, current_lost: bool = False) -> tuple[int, int]:
    """
    (current, best) runs of consecutive solved puzzle numbers. The current run ends at today's puzzle when solved,
    else at yesterday's while today is still open; losing today's puzzle (or missing a day) breaks it.
    """
    number = current if current in won else current - 1
    now = 0
    if not current_lost:
        while number in won:
            now += 1
            number -= 1
    best = run = 0
    previous = None
    for n in sorted(won):
        run = run + 1 if previous is not None and n == previous + 1 else 1
        best = max(best, run)
        previous = n
    return now, best
