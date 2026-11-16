"""
Statement engine: one reader for every bank and both formats, driven by the table layout instead of per-bank
regular expressions.

PDF: words with positions -> rows starting with a date -> numeric columns found from right-aligned amounts
(layout.py) -> roles from the header line (Tarih / Açıklama / Tutar / Borç / Alacak / Bakiye / Taksit / Puan) or,
when a column has no header, from the data (densest column = amount; a column that behaves as a running balance =
balance). Amounts are read in Turkish or US format per number, so a bank switching formats does not break it.

Excel: the header row is found by the same keywords, cells give the columns directly.

Every result is checked against the statement itself: card -> previous balance + rows = statement debt,
account -> running balance. The outcome (ok / mismatch / unknown + message) is shown on the preview, so a missed or
misread row is visible instead of silently imported.
"""

import re
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal

import openpyxl

from . import layout
from .base import ParsedLine, ParsedStatement, StatementParseError
from .profiles import detect_bank, is_card
from .tokens import Amount, Installment, find_date, leading_date, parse_amount
from .utils import card_period, fold

TOLERANCE = Decimal("0.05")
PAYMENT_WORDS = ("odeme", "tesekkur")  # card credits with these words are payments, the rest are refunds
SUMMARY_WORDS = ("onceki donem", "onceki ekstre", "bir onceki", "devir", "toplam")
DEBT_LABELS = ("donem borcunuz", "donem borcu", "ekstre borcu", "hesap ozeti borcu", "toplam borcunuz",
               "guncel donem borcu", "genel toplam")
PREVIOUS_LABELS = ("onceki hesap bakiyesi", "onceki donem bakiyeniz", "bir onceki ekstre bakiyeniz",
                   "onceki donemden devir edilen tutar", "onceki donem hesap ozeti bakiyeniz",
                   "onceki ekstre bakiyesi", "devreden bakiye", "onceki bakiye")
CUT_OFF = re.compile(r"(hesap\s+kesim\s+tarihi|ekstre\s+tarihi|kesim\s+tarihi|hesap\s+özeti\s+tarihi)", re.I)
PREVIOUS_CUT_OFF = re.compile(r"önceki\s+hesap\s+kesim\s+tarihiniz", re.I)
PERIOD = re.compile(r"tarih\s+aral[ıi]ğ[ıi]", re.I)
HOLDER = re.compile(r"^(?:hesap\s+sahibi|ad[ıi]?\s+soyad[ıi]?|müşteri\s+ad[ıi])\s*:?\s*(.+)$", re.I)
CLOSING = re.compile(r"(?<![a-zçğıöşü])bakiye\s*:\s*(\S+)", re.I)

AMOUNT_NOTE = re.compile(r"\s*\([^()]*(?:tutar|TL|₺)[^()]*\)", re.I)  # "(İşlem tutarı: 485,01 TL)"
DESC_TRAILING_AMOUNTS = re.compile(r"(?:\s+[-+]?[\d.,]*\d[.,]\d{2}(?:\s?(?:TL|TRY|USD|EUR|GBP))?)+$")
FAST_BOILERPLATE = re.compile(r"\(\d{2}[./]\d{2}[./]\d{4} tarihli .*\)", re.S)
OUTGOING = re.compile(r"A\.Ş\.\s+(.+?)\s+hesabına giden", re.S)
INCOMING = re.compile(r"A\.Ş\.\s+(.+?)\s+hesabından .*?hesabına gelen", re.S)


# ---------------------------------------------------------------- helpers
def money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def label_amount(lines: list[str], labels: tuple[str, ...]) -> Decimal | None:
    """First amount printed after one of the labels on the same line."""
    for line in lines:
        folded = fold(line)
        for label in labels:
            at = folded.find(label)
            if at < 0:
                continue
            for word in line[at + len(label):].replace(":", " ").split():
                if amount := parse_amount(word):
                    return amount.signed
                if word.isalpha() and fold(word) not in ("tl", "try"):
                    break  # another label starts before any amount
    return None


def label_date(lines: list[str], pattern: re.Pattern, skip=("sonraki",)) -> date | None:
    for line in lines:
        for m in pattern.finditer(line):
            if any(word in fold(line[max(0, m.start() - 16):m.start()]) for word in skip):
                continue
            if found := find_date(line[m.end():].replace(":", " ")):
                return found
    return None


def clean_description(text: str) -> str:
    text = AMOUNT_NOTE.sub("", text)
    text = DESC_TRAILING_AMOUNTS.sub("", text)
    return re.sub(r"\s+", " ", text).strip().rstrip(" -·").lstrip(" ·")[:255]  # a leading "-" can be the name


def describe_account(op_name: str, detail: str) -> str:
    """Operation + counterparty + user note; FAST/EFT boilerplate removed."""
    detail = re.sub(r"\s+", " ", detail or "").strip()
    parts = [op_name.strip()]
    if any(k in op_name.upper() for k in ("FAST", "EFT", "HAVALE")):
        match = OUTGOING.search(detail) or INCOMING.search(detail)
        if match:
            parts.append(match.group(1).strip())
        note = FAST_BOILERPLATE.sub("", detail).strip(" -")
        if note and len(note) <= 80:
            parts.append(note)
    return " · ".join(p for p in parts if p)[:255]


def adjust_installment_date(line_date: date, period_start: date | None, cut_off: date | None, installment: str):
    """Installments of earlier purchases keep the purchase date; book them on the cut-off date of this statement."""
    if installment and period_start and cut_off and line_date < period_start:
        return cut_off
    return line_date


def set_check(result: ParsedStatement, status: str, message: str):
    result.check_status, result.check_message = status, message[:255]


# ---------------------------------------------------------------- PDF
def parse_pdf(path: str) -> ParsedStatement:
    lines = layout.read_lines(path)
    if not any(line.words for line in lines):
        raise StatementParseError("PDF'te okunabilir metin yok (taranmış görüntü olabilir).")
    rows, columns, has_header = layout.table_rows(lines)
    row_lines = {id(r.line) for r in rows}
    meta = [line.text for line in lines if id(line) not in row_lines]
    folded = fold("\n".join(meta))
    card = is_card(folded)
    _resolve_roles(rows, columns, card)
    layout.assign(rows, columns)

    result = ParsedStatement(bank=detect_bank(folded), statement_type="card" if card else "account")
    result.generic = not has_header or result.bank == "other"
    every_line = [line.text for line in lines]
    if card:
        _card(result, rows, every_line)
    else:
        _attach_details(lines, rows, columns)
        _account(result, rows, columns, meta)
    return result


def _densest(columns):
    return max(columns, key=lambda c: c.count, default=None)


def _balance_score(rows, amount_col, balance_col) -> float:
    """Share of consecutive rows where the balance moved exactly by the amount (either row order)."""
    pairs = []
    for r in rows:
        a, b = layout.column_amounts(r, amount_col), layout.column_amounts(r, balance_col)
        if a and b:
            pairs.append((a[0].value, b[0].signed))
    if len(pairs) < 2:
        return 0.0
    forward = sum(abs(abs(b2 - b1) - a2) < TOLERANCE for (_, b1), (a2, b2) in zip(pairs, pairs[1:]))
    backward = sum(abs(abs(b1 - b2) - a1) < TOLERANCE for (a1, b1), (_, b2) in zip(pairs, pairs[1:]))
    return max(forward, backward) / (len(pairs) - 1)


def _resolve_roles(rows, columns, card: bool):
    """Give unlabeled columns a role: densest -> amount; for accounts a running-balance column -> balance."""
    unlabeled = [c for c in columns if not c.role]
    has_amount = any(c.role in ("amount", "debit", "credit") for c in columns)
    balance = next((c for c in columns if c.role == "balance"), None)
    if card:
        if not has_amount and (best := _densest(unlabeled)):
            best.role = "amount"
        return
    if not has_amount and len(unlabeled) >= 2 and not balance:
        # two unnamed columns: the pair that behaves like amount + running balance wins
        candidates = sorted(unlabeled, key=lambda c: -c.count)[:3]
        pairs = [(a, b) for a in candidates for b in candidates if a is not b]
        a, b = max(pairs, key=lambda p: _balance_score(rows, *p))
        a.role, b.role = "amount", "balance"
    elif not has_amount and (best := _densest(unlabeled)):
        best.role = "amount"
    elif has_amount and not balance and unlabeled:
        amount_col = next(c for c in columns if c.role in ("amount", "debit", "credit"))
        best = max(unlabeled, key=lambda c: _balance_score(rows, amount_col, c))
        if _balance_score(rows, amount_col, best) >= 0.8:
            best.role = "balance"


def _attach_details(lines, rows, columns):
    """Account statements: lines under a row (no date, no amount in a money column) continue its description."""
    by_line = {id(r.line): r for r in rows}
    money_cols = [c for c in columns if c.role in layout.MONEY_ROLES]
    current, last_top = None, 0.0
    for line in lines:
        if id(line) in by_line:
            current, last_top = by_line[id(line)], line.top
            continue
        if current is None:
            continue
        text = line.text.strip()
        ends_table = (
            line.page != current.line.page or line.top - last_top > 30 or text.startswith("***")
            or layout.header_labels(line)
            or any(parse_amount(w.text) and c.holds(w) for w in line.words for c in money_cols)
        )
        if ends_table:
            current = None
            continue
        current.detail.append(text)
        last_top = line.top


def _card_amount(row) -> tuple[Amount, bool | None] | None:
    """(amount, credit?) where credit is decided by a debit/credit column, else None (decided by sign markers)."""
    if found := row.amounts("amount"):
        return found[-1], None
    if found := row.amounts("debit"):
        return found[-1], False
    if found := row.amounts("credit"):
        return found[-1], True
    return None


def _summary(row) -> bool:
    return any(word in fold(row.description) for word in SUMMARY_WORDS)


def _purchase_sign(entries, debt, previous) -> str:
    """
    Which printed sign marks a purchase: normally none ("" -> credits carry "+" or "-"). Decided by the payment rows
    ("ÖDEMENİZ İÇİN TEŞEKKÜRLER" are credits), else by which reading matches the statement debt.
    """
    signed = [(row, amount) for row, (amount, side) in entries if side is None and not _summary(row)]
    payment_signs = {a.sign for row, a in signed if any(w in fold(row.description) for w in PAYMENT_WORDS)}
    if len(payment_signs) == 1:
        credit_sign = payment_signs.pop()
        if credit_sign:
            return ""  # payments are marked -> purchases are unmarked
        markers = Counter(a.sign for _, a in signed if a.sign)
        return markers.most_common(1)[0][0] if markers else ""  # payments unmarked -> purchases carry the sign
    if debt is not None:
        for candidate in ("", *sorted({a.sign for _, a in signed if a.sign})):
            net = sum((-a.value if a.sign != candidate else a.value) for _, a in signed)
            if abs((previous or 0) + net - debt) < TOLERANCE or abs(net - debt) < TOLERANCE:
                return candidate
    return ""


def _card(result: ParsedStatement, rows, text_lines: list[str]):
    cut_off = label_date(text_lines, CUT_OFF, skip=("sonraki", "onceki"))
    if cut_off:
        result.period_start, result.period_end = card_period(cut_off)
        if (previous := label_date(text_lines, PREVIOUS_CUT_OFF, skip=())) and previous < cut_off:
            result.period_start = previous + timedelta(days=1)

    entries = [(row, found) for row in rows if (found := _card_amount(row))]
    debt = label_amount(text_lines, DEBT_LABELS)
    previous = label_amount(text_lines, PREVIOUS_LABELS)
    purchase_sign = _purchase_sign(entries, debt, previous)

    previous_row, net = None, Decimal("0")
    for row, (amount, side) in entries:
        folded = fold(row.description)
        if any(word in folded for word in SUMMARY_WORDS):
            if any(word in folded for word in ("onceki", "devir")):
                previous_row = amount.value
            continue
        credit = side if side is not None else amount.sign != purchase_sign
        installment = Installment()
        for word in row.installment_words:
            installment.add_token(word)
        installment.read_description(" ".join(row.installment_words))  # "11.Taksit", plans split over words
        description = clean_description(installment.read_description(row.description))
        expense = -amount.value if credit else amount.value
        net += expense
        is_payment = credit and any(word in fold(description) for word in PAYMENT_WORDS)
        result.lines.append(ParsedLine(
            date=adjust_installment_date(row.date, result.period_start, cut_off, str(installment)),
            description=description or "Kart işlemi",
            amount=-expense,
            raw_text=row.raw,
            installment=str(installment),
            hint="card_payment" if is_payment else "",
        ))

    if previous is None:
        previous = previous_row
    if debt is None:
        set_check(result, "unknown", "Ekstrede dönem borcu bulunamadı; satırları kontrol edin.")
    elif previous is not None and abs(previous + net - debt) < TOLERANCE:
        set_check(result, "ok", f"Ekstre toplamıyla doğrulandı (dönem borcu {money(debt)} TL).")
    elif previous is None and abs(net - debt) < TOLERANCE:
        set_check(result, "ok", f"Ekstre toplamıyla doğrulandı (dönem borcu {money(debt)} TL).")
    else:
        difference = debt - (previous or 0) - net
        set_check(result, "mismatch",
                  f"Okunan satırlar ekstre toplamıyla tutmuyor (fark {money(difference)} TL). Eksik ya da hatalı "
                  "okunan satır olabilir; satırları kontrol edin, gerekirse ekstreyi bize bildirin.")


def _account(result: ParsedStatement, rows, columns, meta: list[str]):
    balance_col = next((c for c in columns if c.role == "balance"), None)
    amounts = []
    for row in rows:
        if found := row.amounts("amount"):
            amounts.append((row, found[0].value, found[0].sign))
        elif found := row.amounts("debit"):
            amounts.append((row, found[0].value, "-"))
        elif found := row.amounts("credit"):
            amounts.append((row, found[0].value, "+"))
    signed_known = any(sign for _, _, sign in amounts)
    balances = [(row.amounts("balance") or [None])[0] for row, _, _ in amounts]

    for i, (row, value, sign) in enumerate(amounts):
        signed = -value if sign == "-" else value
        if not signed_known and balances[i] and i > 0 and balances[i - 1]:
            # no sign printed: direction from the running balance
            if balances[i].signed < balances[i - 1].signed:
                signed = -value
        op_name = row.description
        detail = " ".join(row.detail)
        result.lines.append(ParsedLine(
            date=row.date, description=describe_account(op_name, detail) or "Hesap hareketi", amount=signed,
            raw_text=f"{op_name} {detail}".strip(), external_ref=row.ref,
        ))

    if (m := _first(meta, PERIOD)) and len(dates := _dates(m)) >= 2:
        result.period_start, result.period_end = dates[0], dates[1]
    elif result.lines:
        result.period_start = min(line.date for line in result.lines)
        result.period_end = max(line.date for line in result.lines)
    for line in meta:
        if m := CLOSING.search(line):
            if amount := parse_amount(m.group(1)):
                result.closing_balance = amount.signed
                break
    if result.closing_balance is None and balance_col and balances and balances[-1]:
        result.closing_balance = balances[-1].signed
    result.holder_name = _holder(meta, result.bank)
    _check_balances(result, balances, [v for _, v, _ in amounts])


def _first(lines, pattern):
    return next((line for line in lines if pattern.search(line)), None)


def _dates(text: str) -> list[date]:
    words, found, i = text.replace("-", " ").split(), [], 0
    while i < len(words):
        if hit := leading_date(words[i:i + 3]):
            found.append(hit[0])
            i += hit[1]
        else:
            i += 1
    return found


def _holder(meta: list[str], bank: str) -> str:
    for line in meta[:40]:
        if m := HOLDER.match(line.strip()):
            return m.group(1).strip()[:100]
    if bank == "vakifbank" and len(meta) > 1:
        return meta[1].strip()[:100]  # VakıfBank prints the holder on the second line
    return ""


def _check_balances(result, balances, values):
    pairs = [(v, b.signed) for v, b in zip(values, balances) if b]
    if len(pairs) < 2:
        set_check(result, "unknown", "Bakiye sütunu bulunamadı; satırları kontrol edin.")
        return
    forward = sum(abs(abs(b2 - b1) - v2) < TOLERANCE for (_, b1), (v2, b2) in zip(pairs, pairs[1:]))
    backward = sum(abs(abs(b1 - b2) - v1) < TOLERANCE for (v1, b1), (_, b2) in zip(pairs, pairs[1:]))
    misses = len(pairs) - 1 - max(forward, backward)
    if misses == 0:
        set_check(result, "ok", "Bakiye hareketleriyle doğrulandı.")
    else:
        set_check(result, "mismatch", f"{misses} satırda bakiye tutmuyor. Eksik ya da hatalı okunan satır olabilir; "
                                      "satırları kontrol edin, gerekirse ekstreyi bize bildirin.")


# ---------------------------------------------------------------- Excel
def _cell_text(value) -> str:
    return "" if value is None else str(value).strip()


def _cell_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    found = leading_date(_cell_text(value).split())
    return found[0] if found else None


def _cell_amount(value) -> Amount | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value)).quantize(Decimal("0.01"))
        return Amount(abs(number), "-" if number < 0 else "")
    return parse_amount(_cell_text(value).replace(" ", "").replace("TL", ""))


def _cell_role(text: str) -> tuple[str, int] | None:
    keys = [re.sub(r"[^a-z0-9]", "", fold(w)) for w in text.split()]
    keys = [k for k in keys if k]
    for index, (phrase, role) in enumerate(layout.ROLE_PHRASES):
        if tuple(keys[:len(phrase)]) == phrase or (len(phrase) == 1 and phrase[0] in keys and len(keys) <= 2):
            return role, index
    return None


def parse_xlsx(path: str) -> ParsedStatement:
    sheet = openpyxl.load_workbook(path, data_only=True, read_only=True).worksheets[0]
    table = [list(row) for row in sheet.iter_rows(values_only=True)]
    header_at, columns = None, {}
    for i, row in enumerate(table[:60]):
        found = {}
        for j, value in enumerate(row):
            if (hit := _cell_role(_cell_text(value))) and (hit[0] not in found or hit[1] < found[hit[0]][1]):
                found[hit[0]] = (j, hit[1])
        roles = set(found)
        if "date" in roles and roles & (layout.MONEY_ROLES | {"description"}):
            header_at, columns = i, found
            break
    if header_at is None:
        raise StatementParseError("Excel dosyasında hareket tablosu bulunamadı.")

    meta_cells = [_cell_text(v) for row in table[:header_at] for v in row if _cell_text(v)]
    folded = fold(" ".join(meta_cells))
    card = is_card(folded)
    result = ParsedStatement(bank=detect_bank(folded), statement_type="card" if card else "account")
    result.generic = result.bank == "other"
    pairs = _xlsx_pairs(table[:header_at])
    description_cols = [j for j, value in enumerate(table[header_at]) if (hit := _cell_role(_cell_text(value)))
                        and hit[0] == "description"]
    op_col = next((j for j in description_cols if fold(_cell_text(table[header_at][j])) == "islem"), None)
    detail_cols = [j for j in description_cols if j != op_col]

    get = lambda row, role: row[columns[role][0]] if role in columns and columns[role][0] < len(row) else None  # noqa: E731
    rows, blanks, balances = [], 0, []
    for row in table[header_at + 1:]:
        day = _cell_date(get(row, "date"))
        if day is None:
            blanks += 1
            if rows and blanks >= 3:
                break
            continue
        blanks = 0
        if amount := _cell_amount(get(row, "amount")):
            signed = amount.signed
        elif amount := _cell_amount(get(row, "debit")):
            signed = -amount.value
        elif amount := _cell_amount(get(row, "credit")):
            signed = amount.value
        else:
            continue
        op_name = _cell_text(row[op_col]) if op_col is not None and op_col < len(row) else ""
        detail = " ".join(_cell_text(row[j]) for j in detail_cols if j < len(row) and _cell_text(row[j]))
        if card:
            line = ParsedLine(date=day, description=clean_description(" ".join(filter(None, [op_name, detail]))),
                              amount=-signed if not amount.sign else signed, raw_text=f"{op_name} {detail}".strip())
        else:
            line = ParsedLine(date=day, description=describe_account(op_name or detail, detail if op_name else ""),
                              amount=signed, raw_text=f"{op_name} {detail}".strip(),
                              external_ref=_cell_text(get(row, "ref")))
        rows.append(line)
        balances.append(_cell_amount(get(row, "balance")))
    result.lines = rows

    if holder := pairs.get("hesap sahibi"):
        result.holder_name = holder[:100]
    if balance := pairs.get("bakiye"):
        if amount := parse_amount(balance.replace(" ", "").replace("TL", "")):
            result.closing_balance = amount.signed
    if (period := pairs.get("tarih araligi")) and len(dates := _dates(period)) >= 2:
        result.period_start, result.period_end = dates[0], dates[1]
    elif rows:
        result.period_start, result.period_end = min(r.date for r in rows), max(r.date for r in rows)
    if card:
        set_check(result, "unknown", "Excel kart ekstresi toplamla doğrulanamadı; satırları kontrol edin.")
    else:
        _check_balances(result, balances, [abs(r.amount) for r in rows])
    return result


def _xlsx_pairs(rows) -> dict[str, str]:
    """'LABEL' cell followed by its value cell in the rows above the table (folded label -> value)."""
    pairs = {}
    for row in rows:
        cells = [_cell_text(v) for v in row]
        for i, cell in enumerate(cells):
            if cell and i + 1 < len(cells):
                value = next((c for c in cells[i + 1:i + 3] if c), "")
                pairs.setdefault(fold(cell).rstrip(" :"), value)
    return pairs
