import re

from ..base import BaseParser, ParsedStatement
from ..registry import register
from ..utils import card_period, parse_dmy, pdf_lines, us_amount
from .common import card_line, is_card_summary_row

BANK = "qnb"

# QNB PDFs embed a subset font without unicode map; Turkish letters come out as (cid:N).
CID_MAP = {
    0: "ü", 1: "ş", 2: "ö", 3: "Ö", 4: "Ö", 5: "ğ", 6: "İ", 7: "Ş", 8: "İ", 9: "ş",
    10: "ç", 11: "Ü", 12: "ö", 13: "Ç", 14: "ğ", 20: "ü", 21: "Ş",
}
CID = re.compile(r"\(cid:(\d+)\)")

CARD_ROW = re.compile(r"^(\d{2}/\d{2}/\d{4}) (.+?) (-?[\d,]*\d\.\d{2})(?: (\d+/\d+))?$")


def fix_cid(text: str) -> str:
    return CID.sub(lambda m: CID_MAP.get(int(m.group(1)), ""), text)


@register
class QnbCardPdf(BaseParser):
    key, bank, statement_type, extensions = "qnb_card_pdf", BANK, "card", ("pdf",)

    def detect(self, text):
        return "QNB" in text and "Hesap Kesim Tarihi" in text and "Kredi Kartı" in text

    def parse(self, path):
        lines = [fix_cid(line) for line in pdf_lines(path)]
        text = "\n".join(lines)
        result = ParsedStatement(bank=BANK, statement_type="card")
        cut_off = None
        if m := re.search(r"Hesap Kesim Tarihi : (\d{2}/\d{2}/\d{4})", text):
            cut_off = parse_dmy(m.group(1))
            result.period_start, result.period_end = card_period(cut_off)

        for raw in lines:
            m = CARD_ROW.match(raw)
            if not m:
                continue
            date_text, description, amount_text, installment = m.groups()
            if is_card_summary_row(description):
                continue
            line = card_line(
                line_date=parse_dmy(date_text), description=description, amount=us_amount(amount_text),
                period_start=result.period_start, cut_off=cut_off, installment=installment or "", raw_text=raw,
            )
            if line:
                result.lines.append(line)
        return result
