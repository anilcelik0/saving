import re

from ..base import BaseParser, ParsedStatement
from ..registry import register
from ..utils import card_period, parse_tr_long_date, pdf_lines, tr_amount
from .common import card_line, is_card_summary_row

BANK = "garanti"

DATE = r"\d{1,2} [A-Za-zÇĞİÖŞÜçğıöşü]+ \d{4}"
CARD_ROW = re.compile(rf"^({DATE}) (.+?) ([\d.]+,\d{{2}})(\+)?$")
FILLER = re.compile(r"\s+b+o+s+l+u+k+$", re.I)  # layout filler word "bosluk" at line end
# "1.799,88x12=21.598,56 11.Taksit" -> installment 11/12
INSTALLMENT_PLAN = re.compile(r"\s*[\d.]+,\d{2}x(\d+)=[\d.]+,\d{2}\s+(\d+)\.\s?Taksit", re.I)
INSTALLMENT_SIMPLE = re.compile(r"\s+(\d+/\d+)(?=\s|$)")
ORIGINAL_AMOUNT = re.compile(r"\s+[\d.]+,\d{2}\s?(?:TL|USD|EUR|GBP)$")  # foreign/original amount column
TRAILING_NUMBERS = re.compile(r"(?:\s+-?[\d.]+,\d{2})+$")  # bonus / remaining-debt columns


@register
class GarantiCardPdf(BaseParser):
    """
    Garanti BBVA (Bonus) card statement.
    Row: "<date> <description> [orig amount] [installment plan] [bonus] <amount>[+]" (+ = credit).
    """

    key, bank, statement_type, extensions = "garanti_card_pdf", BANK, "card", ("pdf",)

    def detect(self, text):
        return "Hesap Kesim Tarihi" in text and "garantibbva" in text.lower()

    def parse(self, path):
        lines = pdf_lines(path)
        text = "\n".join(lines)
        result = ParsedStatement(bank=BANK, statement_type="card")
        cut_off = None
        if m := re.search(rf"Hesap Kesim Tarihi ({DATE})", text):
            cut_off = parse_tr_long_date(m.group(1))
            result.period_start, result.period_end = card_period(cut_off)

        for raw in lines:
            row = FILLER.sub("", raw.strip())
            m = CARD_ROW.match(row)
            if not m:
                continue
            date_text, description, amount_text, credit = m.groups()
            if is_card_summary_row(description):
                continue

            installment = ""
            if t := INSTALLMENT_PLAN.search(description):
                installment = f"{t.group(2)}/{t.group(1)}"
                description = description[: t.start()]
            elif t := INSTALLMENT_SIMPLE.search(description):
                installment = t.group(1)
                description = description[: t.start()]
            description = ORIGINAL_AMOUNT.sub("", description)
            description = TRAILING_NUMBERS.sub("", description)

            try:
                line_date = parse_tr_long_date(date_text)
            except (KeyError, ValueError):
                continue
            amount = tr_amount(amount_text)
            line = card_line(
                line_date=line_date, description=description, amount=-amount if credit else amount,
                period_start=result.period_start, cut_off=cut_off, installment=installment, raw_text=raw,
            )
            if line:
                result.lines.append(line)
        return result
