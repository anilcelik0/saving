"""
Timeline mode: one card starts the line, each next card is placed into a gap. A card is right when it fits between
its neighbours (ties allowed). A wrong card costs a life and is discarded. The line wins at `target` cards.
"""

from dataclasses import dataclass, replace
from .status import FINISHED, LOST, PLAYING, WON
from .values import Value, compare

TARGET = 10
LIVES = 3


def deck_size(target: int = TARGET, lives: int = LIVES) -> int:
    """Start card + every card needed to reach the target + one card per life that can be lost."""
    return target + lives


@dataclass(frozen=True)
class TimelineState:
    deck: tuple[str, ...]
    line: tuple[str, ...]  # placed cards, ordered by value
    next_index: int
    lives: int
    target: int = TARGET
    status: str = PLAYING

    @property
    def score(self) -> int:
        """Cards placed correctly (the start card does not count)."""
        return len(self.line) - 1

    @property
    def current(self) -> str | None:
        if self.status != PLAYING or self.next_index >= len(self.deck):
            return None
        return self.deck[self.next_index]


@dataclass(frozen=True)
class PlaceResult:
    state: TimelineState
    card_id: str
    correct: bool
    valid_slots: tuple[int, ...]


def start(deck: list[str], target: int = TARGET, lives: int = LIVES) -> TimelineState:
    if len(deck) < 2:
        raise ValueError("A timeline needs at least two cards.")
    return TimelineState(deck=tuple(deck), line=(deck[0],), next_index=1, lives=lives, target=target)


def valid_slots(line_values: list[Value], value: Value) -> tuple[int, ...]:
    """Gap indexes (0 = before the first card, len = after the last) where the value fits; ties give several."""
    slots = []
    for i in range(len(line_values) + 1):
        left = line_values[i - 1] if i > 0 else None
        right = line_values[i] if i < len(line_values) else None
        if (left is None or compare(left, value) <= 0) and (right is None or compare(value, right) <= 0):
            slots.append(i)
    return tuple(slots)


def place(state: TimelineState, slot: int, values: dict[str, Value]) -> PlaceResult:
    """Apply the move for the current card. `values` must hold the line's cards and the current card."""
    card_id = state.current
    if card_id is None:
        raise ValueError("The run is over.")
    slots = valid_slots([values[c] for c in state.line], values[card_id])
    if not 0 <= slot <= len(state.line):
        raise ValueError("Slot out of range.")
    correct = slot in slots

    line, lives = state.line, state.lives
    if correct:
        line = line[:slot] + (card_id,) + line[slot:]
    else:
        lives -= 1
    next_index = state.next_index + 1
    if len(line) >= state.target:
        status = WON
    elif lives <= 0:
        status = LOST
    elif next_index >= len(state.deck):
        status = FINISHED
    else:
        status = PLAYING
    new_state = replace(state, line=line, lives=lives, next_index=next_index, status=status)
    return PlaceResult(state=new_state, card_id=card_id, correct=correct, valid_slots=slots)
