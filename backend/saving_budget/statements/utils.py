import calendar
import re
from datetime import date, timedelta


TR_MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}


def tr_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def normalize(text: str) -> str:
    """Lowercase (Turkish-aware), collapse whitespace."""
    return re.sub(r"\s+", " ", tr_lower(text or "")).strip()


FOLD = str.maketrans("ıiöüşğç", "iiouşgc".replace("ş", "s"))


def fold(text: str) -> str:
    """Accent-insensitive lowercase for keyword matching: 'MIGROS'/'Mıgros'/'ŞOK' -> 'migros'/'sok'."""
    return normalize(text).translate(FOLD)


def months_before(d: date, months: int = 1) -> date:
    index = d.year * 12 + d.month - 1 - months
    year, month = index // 12, index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def card_period(cut_off: date) -> tuple[date, date]:
    """Card statement period: day after previous cut-off .. cut-off."""
    return months_before(cut_off) + timedelta(days=1), cut_off
