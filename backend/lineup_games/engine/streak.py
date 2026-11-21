"""
Streak mode: one card is open; guess whether the next card's value is higher or lower. Equal values accept either
guess. A right guess extends the streak, a wrong one costs a life; either way the revealed card becomes the open
card. One life; a lost run can be continued a limited number of times (the reward is granted elsewhere).
"""

from dataclasses import dataclass, replace

from .status import FINISHED, LOST, PLAYING
from .values import Value, compare

HIGHER, LOWER = "higher", "lower"
GUESSES = (HIGHER, LOWER)
LIVES = 1
MAX_CONTINUES = 1
DECK_SIZE = 60


@dataclass(frozen=True)
class StreakState:
    deck: tuple[str, ...]
    next_index: int  # the hidden card; the open card is deck[next_index - 1]
    lives: int
    score: int = 0
    continues_used: int = 0
    status: str = PLAYING

    @property
    def open(self) -> str:
        return self.deck[self.next_index - 1]

    @property
    def current(self) -> str | None:
        if self.status != PLAYING or self.next_index >= len(self.deck):
            return None
        return self.deck[self.next_index]


@dataclass(frozen=True)
class GuessResult:
    state: StreakState
    card_id: str
    correct: bool
    relation: str  # the hidden card vs the open one: higher / lower / equal


def start(deck: list[str], lives: int = LIVES) -> StreakState:
    if len(deck) < 2:
        raise ValueError("A streak needs at least two cards.")
    return StreakState(deck=tuple(deck), next_index=1, lives=lives)


def guess(state: StreakState, choice: str, values: dict[str, Value]) -> GuessResult:
    """`values` must hold the open card and the current card."""
    if choice not in GUESSES:
        raise ValueError("Unknown guess.")
    card_id = state.current
    if card_id is None:
        raise ValueError("The run is over.")
    order = compare(values[card_id], values[state.open])
    relation = "equal" if order == 0 else (HIGHER if order > 0 else LOWER)
    correct = relation in ("equal", choice)

    score, lives = state.score, state.lives
    if correct:
        score += 1
    else:
        lives -= 1
    next_index = state.next_index + 1
    if lives <= 0:
        status = LOST
    elif next_index >= len(state.deck):
        status = FINISHED
    else:
        status = PLAYING
    new_state = replace(state, next_index=next_index, lives=lives, score=score, status=status)
    return GuessResult(state=new_state, card_id=card_id, correct=correct, relation=relation)


def can_continue(state: StreakState, max_continues: int = MAX_CONTINUES) -> bool:
    return state.status == LOST and state.continues_used < max_continues and state.next_index < len(state.deck)


def resume(state: StreakState, max_continues: int = MAX_CONTINUES) -> StreakState:
    """One more life after a loss; the streak keeps its score."""
    if not can_continue(state, max_continues):
        raise ValueError("This run cannot be continued.")
    return replace(state, lives=1, continues_used=state.continues_used + 1, status=PLAYING)
