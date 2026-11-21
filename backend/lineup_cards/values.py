"""
Comparable card values: validation, precision and display. Pure Python (no ORM), shared with the game engine.

Dates are stored as year / month / day integers instead of a DateField so that they keep their precision
("1453", "Mayıs 1453", "29 Mayıs 1453") and can go before year 1 (negative year = BC, "MÖ"; there is no year 0).
"""

import calendar
from decimal import Decimal
from enum import StrEnum

MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


class Precision(StrEnum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


def date_precision(month: int | None, day: int | None) -> Precision:
    if day is not None:
        return Precision.DAY
    return Precision.MONTH if month is not None else Precision.YEAR


def date_problems(year: int | None, month: int | None, day: int | None) -> list[str]:
    """Turkish messages for an invalid partial date (empty list = valid)."""
    if year is None:
        return ["Yıl zorunlu."]
    problems = []
    if year == 0:
        problems.append("0 yılı yoktur: MÖ 1 için -1 girin.")
    if day is not None and month is None:
        problems.append("Gün girildiyse ay da girilmeli.")
    if month is not None and not 1 <= month <= 12:
        problems.append("Ay 1 ile 12 arasında olmalı.")
    elif month is not None and day is not None:
        # BC years: leap-agnostic check (29 Şubat allowed)
        last_day = calendar.monthrange(year if year > 0 else 2000, month)[1]
        if not 1 <= day <= last_day:
            problems.append(f"Gün 1 ile {last_day} arasında olmalı.")
    return problems


def format_date(year: int, month: int | None = None, day: int | None = None) -> str:
    """'1453', 'Mayıs 1453', '29 Mayıs 1453', 'MÖ 1200'."""
    text = f"MÖ {-year}" if year < 0 else str(year)
    if month is not None:
        text = f"{MONTHS_TR[month - 1]} {text}"
        if day is not None:
            text = f"{day} {text}"
    return text


def format_number(value: Decimal, decimal_places: int = 0, unit: str = "") -> str:
    """Turkish grouping: Decimal('4479525') -> '4.479.525 kişi', Decimal('11891.5') (1 place) -> '11.891,5 km²'."""
    text = f"{value:,.{decimal_places}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    return f"{text} {unit}".strip()


def decimal_places_of(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0
