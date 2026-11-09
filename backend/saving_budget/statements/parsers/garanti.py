import re

from ..base import BaseParser, ParsedStatement
from ..registry import register
from ..utils import card_period, parse_tr_long_date, pdf_lines, tr_amount
from .common import card_line, is_card_summary_row

BANK = "garanti"

DATE = r"\d{1,2} [A-Za-zÇĞİÖŞÜçğıöşü]+ \d{4}"
CARD_ROW = re.compile(rf"^({DATE}) (.+?) ([\d.]+,\d{{2}})(\+)?$")
TRAILING_INSTALLMENT = re.compile(r"\s+(\d+/\d+)(?:\s+[\d.]+,\d{2})*$")
TRAILING_NUMBERS = re.compile(r"(?:\s+-?[\d.]+,\d{2})+$")  # remaining-debt / bonus columns


@register
class GarantiCardPdf(BaseParser):
    """
    Garanti BBVA (Bonus) card statement.
    NOTE: built from a sample with payment rows only; purchase row layout should be verified with more samples.
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
            m = CARD_ROW.match(raw)
            if not m:
                continue
            date_text, description, amount_text, credit = m.groups()
            if is_card_summary_row(description):
                continue
            installment = ""
            if t := TRAILING_INSTALLMENT.search(description):
                installment = t.group(1)
                description = description[: t.start()]
            description = TRAILING_NUMBERS.sub("", description)
            amount = tr_amount(amount_text)
            if credit:
                amount = -amount  # credit on card (payment or refund)
            try:
                line_date = parse_tr_long_date(date_text)
            except (KeyError, ValueError):
                continue
            line = card_line(
                line_date=line_date, description=description, amount=amount,
                period_start=result.period_start, cut_off=cut_off, installment=installment, raw_text=raw,
            )
            if line:
                result.lines.append(line)
        return result
