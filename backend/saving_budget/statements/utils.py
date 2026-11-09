import calendar
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

import pdfplumber

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


def tr_amount(text: str) -> Decimal:
    """'1.234,56' / '-3,27' / '32.000,00+' -> Decimal (trailing '+' ignored)."""
    clean = text.strip().rstrip("+").replace(".", "").replace(",", ".")
    return Decimal(clean)


def us_amount(text: str) -> Decimal:
    """'1,234.56' / '+21,085.61' / '-173.07' -> Decimal."""
    return Decimal(text.strip().replace(",", ""))


def parse_dmy(text: str) -> date:
    """'15.10.2026' or '15/10/2026'."""
    return datetime.strptime(text.replace("/", "."), "%d.%m.%Y").date()


def parse_tr_long_date(text: str) -> date:
    """'05 Ekim 2026' -> date."""
    day, month, year = text.split()
    return date(int(year), TR_MONTHS[tr_lower(month)], int(day))


def months_before(d: date, months: int = 1) -> date:
    index = d.year * 12 + d.month - 1 - months
    year, month = index // 12, index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def card_period(cut_off: date) -> tuple[date, date]:
    """Card statement period: day after previous cut-off .. cut-off."""
    return months_before(cut_off) + timedelta(days=1), cut_off


def pdf_lines(path: str) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [line for page in pdf.pages for line in (page.extract_text() or "").splitlines()]


def first_page_text(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            return ""
        return pdf.pages[0].extract_text() or ""
