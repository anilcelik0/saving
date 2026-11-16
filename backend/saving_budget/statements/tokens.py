"""
Word-level parsing used by the statement engine: amounts in Turkish ("1.234,56") or US ("1,234.56") format with
sign markers, dates ("15.10.2026", "15/10/26", "05 Ekim 2026"), and installment notes ("2/6", "3. Taksit",
"1.799,88x12=21.598,56", "2x1.136,50", "Son Taksit").
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .utils import TR_MONTHS, fold

# one word: [sign] digits with thousands groups [., ] decimal [., ] 2 digits [sign] [currency]
AMOUNT_WORD = re.compile(
    r"^(?P<pre>[+-])?(?P<int>\d{1,3}(?:(?P<th>[.,])\d{3})(?:(?P=th)\d{3})*|\d+)(?P<dec>[.,])(?P<cents>\d{2})"
    r"(?P<post>[+-])?(?:TL|TRY|₺)?$"
)
CURRENCY_WORDS = {"tl", "try", "₺"}
SIGN_WORDS = {"-", "+"}

DATE_WORD = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})$")
TIME_WORD = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
MONTH_ABBR = {fold(name)[:3]: number for name, number in TR_MONTHS.items()}
MONTHS = {fold(name): number for name, number in TR_MONTHS.items()} | MONTH_ABBR


@dataclass
class Amount:
    value: Decimal  # absolute value
    sign: str  # "+", "-" or "" (as printed)

    @property
    def signed(self) -> Decimal:
        return -self.value if self.sign == "-" else self.value


def parse_amount(word: str) -> Amount | None:
    m = AMOUNT_WORD.match(word.strip())
    if not m or (m["th"] and m["th"] == m["dec"]):
        return None
    integer = m["int"].replace(".", "").replace(",", "")
    return Amount(Decimal(f"{integer}.{m['cents']}"), m["pre"] or m["post"] or "")


def _safe_date(year: int, month: int, day: int) -> date | None:
    if year < 100:
        year += 2000
    if not 2000 <= year <= 2100:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def leading_date(words: list[str]) -> tuple[date, int] | None:
    """Date at the start of a row -> (date, number of words used)."""
    if not words:
        return None
    if m := DATE_WORD.match(words[0]):
        d = _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return (d, 1) if d else None
    if len(words) >= 3 and words[0].isdigit() and len(words[0]) <= 2 and re.fullmatch(r"\d{4}", words[2]):
        month = MONTHS.get(fold(words[1])) or MONTHS.get(fold(words[1])[:3])
        if month:
            d = _safe_date(int(words[2]), month, int(words[0]))
            return (d, 3) if d else None
    return None


def find_date(text: str) -> date | None:
    """First date anywhere in a text."""
    words = text.split()
    for i in range(len(words)):
        if found := leading_date(words[i:i + 3]):
            return found[0]
    return None


def is_time(word: str) -> bool:
    return bool(TIME_WORD.match(word))


# ---------------------------------------------------------------- installments
FRACTION = re.compile(r"^(\d{1,2})/(\d{1,2})$")
ORDINAL = re.compile(r"(\d{1,2})\s*\.\s*taksit")  # folded text: "3. taksit", "11.taksit"
PLAN = re.compile(r"[\d.,]+x(\d{1,2})=[\d.,]+")  # 1.799,88x12=21.598,56 -> 12 installments
REMAINING_X = re.compile(r"^(\d{1,2})x[\d.,]+$")  # 2x1.136,50 -> 2 installments left


@dataclass
class Installment:
    number: int | None = None
    total: int | None = None
    remaining: int | None = None
    last: bool = False

    def add_token(self, token: str) -> bool:
        """Installment-column token; True if it was installment info."""
        t = fold(token)
        if m := FRACTION.match(t):
            self.number, self.total = int(m.group(1)), int(m.group(2))
        elif m := REMAINING_X.match(t):
            self.remaining = int(m.group(1))
        elif m := PLAN.search(t):
            self.total = int(m.group(1))
        elif t.isdigit() and len(t) <= 2:
            self.remaining = int(t)
        elif t in ("son", "taksit"):
            self.last = self.last or t == "son"
        else:
            return False
        return True

    def read_description(self, text: str) -> str:
        """Takes "3. Taksit", "AxN=T" and "Son Taksit" out of a description; returns the rest."""
        folded = fold(text)
        if m := ORDINAL.search(folded):
            self.number = self.number or int(m.group(1))
        if m := PLAN.search(folded):
            self.total = self.total or int(m.group(1))
        if "son taksit" in folded:
            self.last = True
        text = re.sub(r"\s*\d{1,2}\s*\.\s*[Tt][Aa][Kk][Ss][İIiı][Tt]\b", "", text)
        text = re.sub(r"\s*[\d.,]+x\d{1,2}=[\d.,]+", "", text)
        return re.sub(r"\s*\b[Ss][Oo][Nn]\s+[Tt][Aa][Kk][Ss][İIiı][Tt]\b", "", text)

    def __str__(self):
        n, total = self.number, self.total
        if n and not total:
            if self.remaining is not None:
                total = n + self.remaining
            elif self.last:
                total = n
        if n and total:
            return f"{n}/{total}"
        if n:
            return f"{n}. taksit"
        if self.remaining:
            return f"kalan {self.remaining}"
        return ""
