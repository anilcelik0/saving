import re

from ..base import BaseParser, ParsedStatement
from ..cid import decode_lines
from ..registry import register
from ..utils import card_period, fold, parse_dmy, pdf_lines, tr_amount
from .common import card_line, is_card_summary_row

BANK = "enpara"

# "24/12/2025 YENİ ASYA ECZANESİ (İşlem tutarı: 485,01 TL) 2/6 80,83 TL"
# "25/01/2026 Ödeme - Enpara.com Cep Şubesi - 11.906,14 TL"
CARD_ROW = re.compile(r"^(\d{2}/\d{2}/\d{4}) (.+?)(?: (\d{1,2}/\d{1,2}))? (- )?([\d.]+,\d{2}) TL$")
AMOUNT_NOTE = re.compile(r"\s*\([^()]*(?:tutar|TL)[^()]*\)", re.I)


@register
class EnparaCardPdf(BaseParser):
    """Enpara credit card statement (fonts without unicode map -> cid decoder)."""

    key, bank, statement_type, extensions = "enpara_card_pdf", BANK, "card", ("pdf",)

    def detect(self, text):
        return "Enpara" in text and "Kredi Kartı Ekstresi" in text

    def parse(self, path):
        lines = decode_lines(pdf_lines(path))
        text = "\n".join(lines)
        result = ParsedStatement(bank=BANK, statement_type="card")
        cut_off = None
        if m := re.search(r"Ekstre tarihi (\d{2}/\d{2}/\d{4})", text):
            cut_off = parse_dmy(m.group(1))
            result.period_start, result.period_end = card_period(cut_off)

        for raw in lines:
            m = CARD_ROW.match(raw.strip())
            if not m:
                continue
            date_text, description, installment, credit, amount_text = m.groups()
            if is_card_summary_row(description):
                continue
            if credit and "odeme" in fold(description):
                continue  # card payment; purchases are imported one by one
            amount = tr_amount(amount_text)
            line = card_line(
                line_date=parse_dmy(date_text),
                description=AMOUNT_NOTE.sub("", description).strip(" -"),
                amount=-amount if credit else amount,  # credit = refund
                period_start=result.period_start, cut_off=cut_off, installment=installment or "", raw_text=raw,
            )
            if line:
                result.lines.append(line)
        return result
