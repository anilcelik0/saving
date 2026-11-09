"""
Fallback parser for banks without a dedicated parser (registered LAST, accepts any PDF).

Heuristics:
  - transaction row = line starting with a date and ending with an amount
    ("15/01/2026 MIGROS 1.234,56 TL", "05 Ekim 2026 ... 32.000,00+", "2/6 80,83 TL" installments)
  - account statements may end with "amount balance" -> the first of the two is the amount
  - card vs account decided by keywords; card rows: positive = expense, "-"/"+" credit = payment/refund
  - card period from "Hesap Kesim / Ekstre tarihi"; earlier-period installments booked on cut-off date
Lines should be reviewed by the user (preview shows a warning for generic parses).
"""

import re
from decimal import Decimal

from ..base import BaseParser, ParsedLine, ParsedStatement
from ..cid import decode_lines
from ..registry import register
from ..utils import TR_MONTHS, card_period, fold, parse_dmy, parse_tr_long_date, pdf_lines
from .common import card_line, is_card_summary_row

MONTHS = "|".join(sorted({m.capitalize() for m in TR_MONTHS} | set(TR_MONTHS), key=len, reverse=True))
DATE = rf"\d{{2}}[./-]\d{{2}}[./-]\d{{4}}|\d{{1,2}} (?:{MONTHS}) \d{{4}}"
AMOUNT = r"[-+]?\s?(?:\d{1,3}(?:[.,]\d{3})+|\d+)[.,]\d{2}(?:\s?(?:TL|TRY|₺))?[+-]?"
INSTALLMENT = r"\d{1,2}/\d{1,2}"
TRAILING_EXTRAS = r"(?:\s+(?:\d{1,2}|\d+x[\d.,]+|\*))*"  # remaining-installment count, "1x581.50", reward marker
# "date description [n/m] amount [balance|n/m] [extras]"
ROW = re.compile(
    rf"^({DATE})\s+(.+?)\s+(?:({INSTALLMENT})\s+)?({AMOUNT})(?:\s+({AMOUNT}|{INSTALLMENT}))?{TRAILING_EXTRAS}$"
)
# account layout "date [time] [ref] amount balance description"
ROW_AMOUNT_FIRST = re.compile(rf"^({DATE})(?:\s+\d{{2}}:\d{{2}})?(?:\s+\d{{6,}})?\s+({AMOUNT})\s+({AMOUNT})\s+(\D.*)$")
CUT_OFF = re.compile(rf"(?:hesap kesim tarihi|ekstre tarihi|kesim tarihi)\s*:?\s*({DATE})", re.I)
AMOUNT_NOTE = re.compile(r"\s*\([^()]*(?:tutar|TL|₺)[^()]*\)", re.I)  # "(İşlem tutarı: 485,01 TL)"

CARD_HINTS = ("ekstre borcu", "donem borcu", "son odeme tarihi", "hesap kesim", "kart limiti", "asgari odeme")
BANK_NAMES = [
    ("enpara", "enpara"), ("akbank", "akbank"), ("ziraat", "ziraat"), ("is bankasi", "isbank"),
    ("isbank", "isbank"), ("yapi kredi", "yapikredi"), ("halkbank", "halkbank"), ("denizbank", "denizbank"),
    ("kuveyt turk", "kuveytturk"), ("ing bank", "ing"), ("teb", "teb"), ("fibabanka", "fibabanka"),
    ("sekerbank", "sekerbank"), ("albaraka", "albaraka"), ("odeabank", "odeabank"), ("papara", "papara"),
    ("vakifbank", "vakifbank"), ("garanti", "garanti"), ("qnb", "qnb"),
]


def parse_amount(token: str) -> Decimal:
    """Any TR/US formatted amount with optional sign/currency -> signed Decimal."""
    t = re.sub(r"\s|TL|TRY|₺", "", token)
    negative = t.startswith("-") or t.endswith("-")
    t = t.strip("+-")
    value = Decimal(t[:-3].replace(".", "").replace(",", "") + "." + t[-2:])  # last 3 chars: separator + cents
    return -value if negative else value


def parse_any_date(text: str):
    return parse_dmy(text.replace("-", ".")) if text[2] in "./-" else parse_tr_long_date(text)


def detect_bank(folded_text: str) -> str:
    return next((slug for name, slug in BANK_NAMES if re.search(rf"(?<![a-z]){name}(?![a-z])", folded_text)), "other")


@register
class GenericPdf(BaseParser):
    key, bank, statement_type, extensions = "generic_pdf", "other", "", ("pdf",)
    generic = True

    def detect(self, text):
        return True

    def parse(self, path):
        lines = decode_lines(pdf_lines(path))
        text = "\n".join(lines)
        folded = fold(text)
        is_card = any(h in folded for h in CARD_HINTS)
        result = ParsedStatement(bank=detect_bank(folded), statement_type="card" if is_card else "account")

        cut_off = None
        if m := CUT_OFF.search(text):
            cut_off = parse_any_date(m.group(1))
            if is_card:
                result.period_start, result.period_end = card_period(cut_off)

        for raw in lines:
            raw = raw.strip()
            if m := ROW.match(raw):
                date_text, description, installment, first_amount, second = m.groups()
                if second and "/" in second:
                    installment = second  # "amount n/m" layout
            elif not is_card and (m := ROW_AMOUNT_FIRST.match(raw)):
                date_text, first_amount, _balance, description = m.groups()
                installment = None
            else:
                continue
            if is_card_summary_row(description):
                continue
            try:
                line_date = parse_any_date(date_text)
            except (KeyError, ValueError):
                continue
            # "- 11.906,14 TL" style: a dash right before the amount belongs to the amount
            if description.endswith(" -"):
                description, first_amount = description[:-2], "-" + first_amount
            description = AMOUNT_NOTE.sub("", description).strip(" -")
            if not installment and (t := re.search(r"(\d+)\.\s?taksit", fold(description))):
                installment = f"{t.group(1)}. taksit"
            amount = parse_amount(first_amount)
            is_credit = amount < 0 or first_amount.strip().endswith("+") or first_amount.strip().startswith("+")

            if is_card:
                if is_credit and "odeme" in fold(description):
                    continue  # card payment row (purchases are imported one by one)
                line = card_line(
                    line_date=line_date, description=description, amount=-abs(amount) if is_credit else abs(amount),
                    period_start=result.period_start, cut_off=cut_off, installment=installment or "", raw_text=raw,
                )
                if line:
                    result.lines.append(line)
            else:
                # account: shown sign is the money direction; second amount (if any) is the running balance
                result.lines.append(ParsedLine(
                    date=line_date, description=re.sub(r"\s+", " ", description)[:255], amount=amount, raw_text=raw,
                ))
        return result
