"""Card values as the engine sees them, and the comparison rule (ties included)."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Value:
    """A number, or a partial date (year / month / day; negative year = BC)."""

    number: Decimal | None = None
    year: int | None = None
    month: int | None = None
    day: int | None = None

    @property
    def is_date(self) -> bool:
        return self.year is not None

    def date_parts(self) -> tuple[int, ...]:
        """(year,), (year, month) or (year, month, day): the length is the precision."""
        if self.day is not None:
            return self.year, self.month, self.day
        if self.month is not None:
            return self.year, self.month
        return (self.year,)


def compare(a: Value, b: Value) -> int:
    """
    -1 / 0 / 1. Dates are compared at the coarser precision of the two, so "2001" equals "3 May 2001"
    (either order is accepted); numbers are equal only when exactly equal.
    """
    if a.is_date != b.is_date:
        raise ValueError("A date cannot be compared with a number.")
    if a.is_date:
        pa, pb = a.date_parts(), b.date_parts()
        n = min(len(pa), len(pb))
        left, right = pa[:n], pb[:n]
    else:
        left, right = a.number, b.number
    return (left > right) - (left < right)


def gap(a: Value, b: Value) -> float:
    """Distance used for difficulty: whole years for dates, relative difference (0..1) for numbers."""
    if a.is_date:
        return abs(a.year - b.year)
    largest = max(abs(a.number), abs(b.number))
    return float(abs(a.number - b.number) / largest) if largest else 0.0
