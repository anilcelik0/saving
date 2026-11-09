import re
from datetime import date

from ..base import ParsedLine


def adjust_installment_date(line_date: date, period_start: date | None, cut_off: date | None, installment: str) -> date:
    """
    Card installments from earlier purchases keep the original purchase date on the statement.
    Book them on the statement cut-off date so they fall into the right month.
    Non-installment rows keep their date (e.g. purchases on the previous cut-off day).
    """
    if installment and period_start and cut_off and line_date < period_start:
        return cut_off
    return line_date


def card_line(
    *, line_date, description, amount, period_start, cut_off, installment="", raw_text=""
) -> ParsedLine | None:
    """
    Card statement row -> ParsedLine. amount: positive = purchase (expense), negative = refund.
    Payment rows ("ödemeniz için teşekkürler") are dropped: purchases are imported one by one.
    """
    text = description.upper()
    if "ÖDEMENİZ" in text or "ODEMENIZ" in text:
        return None
    return ParsedLine(
        date=adjust_installment_date(line_date, period_start, cut_off, installment),
        description=re.sub(r"\s+", " ", description).strip()[:255],
        amount=-amount,
        installment=installment,
        raw_text=raw_text or description,
    )


CARD_SKIP_MARKERS = ("ÖNCEKİ DÖNEM", "ONCEKI DONEM", "TOPLAM", "DEVİR")


def is_card_summary_row(description: str) -> bool:
    upper = description.upper()
    return any(marker in upper for marker in CARD_SKIP_MARKERS)
