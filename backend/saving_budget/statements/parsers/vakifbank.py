import re
from decimal import Decimal

import openpyxl

from ..base import BaseParser, ParsedLine, ParsedStatement
from ..registry import register
from ..utils import card_period, parse_dmy, pdf_lines, tr_amount, us_amount
from .common import card_line, is_card_summary_row

BANK = "vakifbank"

ACCOUNT_ROW = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4}) (\d{2}:\d{2}) (\d{10,}) (-?[\d.]+,\d{2}) (-?[\d.]+,\d{2}) (.+)$"
)
FAST_BOILERPLATE = re.compile(r"\(\d{2}[./]\d{2}[./]\d{4} tarihli .*\)", re.S)
OUTGOING = re.compile(r"A\.Ş\.\s+(.+?)\s+hesabına giden", re.S)
INCOMING = re.compile(r"A\.Ş\.\s+(.+?)\s+hesabından .*?hesabına gelen", re.S)


def account_description(op_name: str, detail: str) -> str:
    """Readable description: operation name + counterparty + user note (FAST/EFT boilerplate removed)."""
    detail = re.sub(r"\s+", " ", detail or "").strip()
    parts = [op_name.strip()]
    if "FAST" in op_name.upper() or "EFT" in op_name.upper() or "HAVALE" in op_name.upper():
        match = OUTGOING.search(detail) or INCOMING.search(detail)
        if match:
            parts.append(match.group(1).strip())
        note = FAST_BOILERPLATE.sub("", detail).strip(" -")
        if note and len(note) <= 80:
            parts.append(note)
    return " · ".join(parts)[:255]


def account_line(date_text, ref, amount, op_name, detail) -> ParsedLine:
    return ParsedLine(
        date=parse_dmy(date_text),
        description=account_description(op_name, detail),
        amount=amount,
        raw_text=f"{op_name} {detail}".strip(),
        external_ref=ref,
    )


@register
class VakifbankAccountPdf(BaseParser):
    key, bank, statement_type, extensions = "vakifbank_account_pdf", BANK, "account", ("pdf",)

    def detect(self, text):
        return "Hesap Hareketleri" in text and "VB Müş. No" in text

    def parse(self, path):
        lines = pdf_lines(path)
        text = "\n".join(lines)
        result = ParsedStatement(bank=BANK, statement_type="account")
        if m := re.search(r"Tarih Aralığı : (\d{2}\.\d{2}\.\d{4}) - (\d{2}\.\d{2}\.\d{4})", text):
            result.period_start, result.period_end = parse_dmy(m.group(1)), parse_dmy(m.group(2))
        if m := re.search(r"Bakiye : (-?[\d.]+,\d{2}) TL", text):
            result.closing_balance = tr_amount(m.group(1))
        if len(lines) > 1:
            result.holder_name = lines[1]

        current, in_table = None, False
        for raw in lines:
            if raw.startswith("TARİH SAAT İŞLEM NO"):
                in_table = True
                continue
            if raw.startswith("***"):  # page footer; vertical watermark text follows
                in_table = False
                continue
            if not in_table:
                continue
            if m := ACCOUNT_ROW.match(raw):
                if current:
                    result.lines.append(account_line(*current))
                date_text, _, ref, amount, _, op_name = m.groups()
                current = [date_text, ref, tr_amount(amount), op_name, ""]
            elif current:
                current[4] = f"{current[4]} {raw}".strip()
        if current:
            result.lines.append(account_line(*current))
        return result


@register
class VakifbankAccountXlsx(BaseParser):
    key, bank, statement_type, extensions = "vakifbank_account_xlsx", BANK, "account", ("xlsx",)

    def detect(self, workbook):
        ws = workbook.worksheets[0]
        for row in ws.iter_rows(min_row=1, max_row=8, values_only=True):
            if row and row[0] == "VB MÜŞTERİ NO":
                return True
        return False

    def parse(self, path):
        ws = openpyxl.load_workbook(path, data_only=True, read_only=True).worksheets[0]
        result = ParsedStatement(bank=BANK, statement_type="account")
        columns = None
        for row in ws.iter_rows(values_only=True):
            if columns is None:
                info = {row[i]: row[i + 1] for i in (0, 6) if len(row) > i + 1 and row[i]}
                if holder := info.get("HESAP SAHİBİ"):
                    result.holder_name = str(holder)
                if balance := info.get("BAKİYE"):
                    result.closing_balance = tr_amount(str(balance).replace("TL", ""))
                if period := info.get("TARİH ARALIĞI"):
                    start, end = (p.strip() for p in str(period).split("-"))
                    result.period_start, result.period_end = parse_dmy(start), parse_dmy(end)
                if "TUTAR" in row and "İŞLEM TARİHİ" in row:
                    columns = {name: i for i, name in enumerate(row) if name}
                continue
            if not row[columns["İŞLEM TARİHİ"]]:
                break
            value = row[columns["TUTAR"]]
            result.lines.append(
                account_line(
                    str(row[columns["İŞLEM TARİHİ"]]),
                    str(row[columns["İŞLEM NO"]] or ""),
                    Decimal(str(value)).quantize(Decimal("0.01")),
                    str(row[columns["İŞLEM"]] or ""),
                    str(row[columns["AÇIKLAMA"]] or ""),
                )
            )
        return result


CARD_ROW = re.compile(r"^(\d{2}\.\d{2}\.\d{4}) (.+?) ([+-]?[\d,]*\d\.\d{2})(?: (\d+x[\d,.]+|\d+))?(?: \*)?$")


@register
class VakifbankCardPdf(BaseParser):
    key, bank, statement_type, extensions = "vakifbank_card_pdf", BANK, "card", ("pdf",)

    def detect(self, text):
        return "Kredi Kartı Hesap Özeti" in text and "VB Müşteri No" in text

    def parse(self, path):
        lines = pdf_lines(path)
        text = "\n".join(lines)
        result = ParsedStatement(bank=BANK, statement_type="card")
        cut_off = None
        if m := re.search(r"Hesap Kesim Tarihi : (\d{2}\.\d{2}\.\d{4})", text):
            cut_off = parse_dmy(m.group(1))
            result.period_start, result.period_end = card_period(cut_off)

        for raw in lines:
            m = CARD_ROW.match(raw)
            if not m:
                continue
            date_text, description, amount_text, extra = m.groups()
            if is_card_summary_row(description):
                continue
            installment = ""
            if extra and extra.isdigit():
                installment = f"kalan {extra}"
            elif t := re.search(r"(\d+)\. Taksit", description, re.I):
                installment = f"{t.group(1)}. taksit"
            amount = us_amount(amount_text)
            if amount_text.startswith("+"):
                amount = -amount  # credit on card (payment or refund)
            line = card_line(
                line_date=parse_dmy(date_text), description=description, amount=amount,
                period_start=result.period_start, cut_off=cut_off, installment=installment, raw_text=raw,
            )
            if line:
                result.lines.append(line)
        return result
