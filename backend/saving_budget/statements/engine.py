"""
Statement engine: one reader for every bank and both formats, driven by the table layout instead of per-bank
regular expressions.

PDF: words with positions -> rows starting with a date -> numeric columns found from right-aligned amounts
(layout.py) -> roles from the header line (Tarih / Açıklama / Tutar / Borç / Alacak / Bakiye / Taksit / Puan) or,
when a column has no header, from the data (densest column = amount; a column that behaves as a running balance =
balance). Amounts are read in Turkish or US format per number, so a bank switching formats does not break it.

Excel: the header row is found by the same keywords, cells give the columns directly.

Every result is checked against the statement itself: card -> the summary's own totals (card.py, summary.py),
account -> running balance row by row and the closing balance. The outcome (ok / mismatch / unknown + message,
every check, flags on the lines that need a look) is shown on the preview, so a missed or misread row is visible
instead of silently imported. Label words: vocabulary.py.
"""

import re
from datetime import date, datetime
from decimal import Decimal

import openpyxl

from . import card, layout, summary
from .base import ParsedLine, ParsedStatement, StatementParseError
from .profiles import detect_bank, is_card
from .tokens import Amount, find_date, leading_date, parse_amount
from .utils import card_period, fold
from .vocabulary import CLOSING, CUT_OFF, HOLDER, PERIOD, ROLE_PHRASES  # noqa: F401 - HOLDER used by samples.py

ENGINE_VERSION = "2026.11.28"  # stored with every read (StatementReadLog): quality per engine version
TOLERANCE = Decimal("0.05")

AMOUNT_NOTE = re.compile(r"\s*\([^()]*(?:tutar|TL|₺)[^()]*\)", re.I)  # "(İşlem tutarı: 485,01 TL)"
DESC_TRAILING_AMOUNTS = re.compile(r"(?:\s+[-+]?[\d.,]*\d[.,]\d{2}(?:\s?(?:TL|TRY|USD|EUR|GBP))?)+$")
FAST_BOILERPLATE = re.compile(r"\(\d{2}[./]\d{2}[./]\d{4} tarihli .*\)", re.S)
OUTGOING = re.compile(r"A\.Ş\.\s+(.+?)\s+hesabına giden", re.S)
INCOMING = re.compile(r"A\.Ş\.\s+(.+?)\s+hesabından .*?hesabına gelen", re.S)


# ---------------------------------------------------------------- helpers
money = card.money


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


def set_check(result: ParsedStatement, status: str, message: str):
    result.check_status, result.check_message = status, message[:255]


# ---------------------------------------------------------------- PDF
def parse_pdf(path: str) -> ParsedStatement:
    return parse_pdf_pages(layout.extract_pages(path))


def parse_pdf_pages(pages: list[list[dict]]) -> ParsedStatement:
    """Words per page (layout.extract_pages or a sample fixture) -> parsed statement."""
    lines = layout.lines_from_pages(pages)
    if not any(line.words for line in lines):
        raise StatementParseError("PDF'te okunabilir metin yok (taranmış görüntü olabilir).")
    rows, columns, has_header = layout.table_rows(lines)
    row_lines = {id(r.line) for r in rows}
    meta = [line.text for line in lines if id(line) not in row_lines]
    folded = fold("\n".join(meta))
    is_card_statement = is_card(folded)
    _resolve_roles(rows, columns, is_card_statement)
    layout.assign(rows, columns)

    result = ParsedStatement(bank=detect_bank(folded), statement_type="card" if is_card_statement else "account")
    result.generic = not has_header or result.bank == "other"
    if is_card_statement:
        card.read_pdf(result, lines, rows, columns, [line.text for line in lines])
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


def _resolve_roles(rows, columns, is_card_statement: bool):
    """Give unlabeled columns a role: densest -> amount; for accounts a running-balance column -> balance."""
    unlabeled = [c for c in columns if not c.role]
    has_amount = any(c.role in ("amount", "debit", "credit") for c in columns)
    balance = next((c for c in columns if c.role == "balance"), None)
    if is_card_statement:
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
    printed_closing = None
    for line in meta:
        if m := CLOSING.search(line):
            if amount := parse_amount(m.group(1)):
                printed_closing = result.closing_balance = amount.signed
                break
    if result.closing_balance is None and balance_col and balances and balances[-1]:
        result.closing_balance = balances[-1].signed
    result.holder_name = _holder(meta, result.bank)
    check_balances(result, [b.signed if b else None for b in balances], [v for _, v, _ in amounts], printed_closing)


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


def check_balances(result: ParsedStatement, balances: list, values: list, printed_closing=None):
    """Running balance: each row must move the balance by its amount (rows printed oldest or newest first).
    The row where it does not is flagged; the last balance must equal a printed closing balance."""
    lines = result.lines
    known = [i for i, b in enumerate(balances) if b is not None]
    if len(known) < 2:
        set_check(result, "unknown", "Bakiye sütunu bulunamadı; satırları kontrol edin.")
        return
    pairs = list(zip(known, known[1:]))
    forward = [abs(abs(balances[j] - balances[i]) - values[j]) < TOLERANCE for i, j in pairs]
    backward = [abs(abs(balances[i] - balances[j]) - values[i]) < TOLERANCE for i, j in pairs]
    oldest_first = sum(forward) >= sum(backward)
    breaks = [j if oldest_first else i for (i, j), ok in zip(pairs, forward if oldest_first else backward) if not ok]
    for index in breaks:
        lines[index].flag("balance_break", "Bakiye bu satırda tutmuyor: tutar ya da yön hatalı okunmuş, ya da "
                                           "yakınında bir satır eksik olabilir.")
    result.checks.append({"code": "running_balance", "label": "Satır satır bakiye",
                          "expected": str(len(pairs)), "actual": str(len(pairs) - len(breaks)), "ok": not breaks})
    closing_ok = True
    if printed_closing is not None:
        last = balances[known[-1]] if oldest_first else balances[known[0]]
        closing_ok = abs(last - printed_closing) < TOLERANCE
        result.checks.append({"code": "closing", "label": "Kapanış bakiyesi", "expected": str(printed_closing),
                              "actual": str(last), "ok": closing_ok})
    if not breaks and closing_ok:
        set_check(result, "ok", "Bakiye hareketleriyle doğrulandı.")
    elif breaks:
        first = lines[breaks[0]]
        set_check(result, "mismatch", f"{len(breaks)} satırda bakiye tutmuyor (ilki {first.date:%d.%m.%Y} "
                                      f"'{first.description[:40]}'). Eksik ya da hatalı okunan satır olabilir; "
                                      "işaretli satırları kontrol edin, gerekirse ekstreyi bize bildirin.")
    else:
        set_check(result, "mismatch", "Satırlar birbiriyle tutuyor ama son bakiye ekstredeki bakiyeden farklı: "
                                      "ekstrenin sonunda okunmamış satır olabilir.")


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
    for index, (phrase, role) in enumerate(ROLE_PHRASES):
        if tuple(keys[:len(phrase)]) == phrase or (len(phrase) == 1 and phrase[0] in keys and len(keys) <= 2):
            return role, index
    return None


def read_table(path: str) -> list[list]:
    """The reader's whole input from an Excel file: cell values of the first sheet."""
    sheet = openpyxl.load_workbook(path, data_only=True, read_only=True).worksheets[0]
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def parse_xlsx(path: str) -> ParsedStatement:
    return parse_table(read_table(path))


def find_header(table: list[list]) -> tuple[int | None, dict]:
    """Index of the transaction table's header row + {role: (column index, phrase rank)}."""
    for i, row in enumerate(table[:60]):
        found = {}
        for j, value in enumerate(row):
            if (hit := _cell_role(_cell_text(value))) and (hit[0] not in found or hit[1] < found[hit[0]][1]):
                found[hit[0]] = (j, hit[1])
        roles = set(found)
        if "date" in roles and roles & (layout.MONEY_ROLES | {"description"}):
            return i, found
    return None, {}


def _text_lines(rows: list[list]) -> list[layout.Line]:
    """Excel rows above the table as text lines (for the summary reader): cells side by side."""
    out = []
    for n, row in enumerate(rows):
        words = [w for cell in row if (text := _cell_text(cell)) for w in text.split()]
        out.append(layout.Line([layout.Word(w, i * 10.0, i * 10.0 + 8, float(n), 0) for i, w in enumerate(words)],
                               0, float(n)))
    return out


def parse_table(table: list[list]) -> ParsedStatement:
    """Cell values (read_table or a sample fixture) -> parsed statement."""
    header_at, columns = find_header(table)
    if header_at is None:
        raise StatementParseError("Excel dosyasında hareket tablosu bulunamadı.")

    meta_cells = [_cell_text(v) for row in table[:header_at] for v in row if _cell_text(v)]
    folded = fold(" ".join(meta_cells))
    is_card_statement = is_card(folded)
    result = ParsedStatement(bank=detect_bank(folded), statement_type="card" if is_card_statement else "account")
    result.generic = result.bank == "other"
    pairs = _xlsx_pairs(table[:header_at])
    description_cols = [j for j, value in enumerate(table[header_at]) if (hit := _cell_role(_cell_text(value)))
                        and hit[0] == "description"]
    op_col = next((j for j in description_cols if fold(_cell_text(table[header_at][j])) == "islem"), None)
    detail_cols = [j for j in description_cols if j != op_col]

    get = lambda row, role: row[columns[role][0]] if role in columns and columns[role][0] < len(row) else None  # noqa: E731
    lines, entries, blanks, balances = [], [], 0, []
    for row in table[header_at + 1:]:
        day = _cell_date(get(row, "date"))
        if day is None:
            blanks += 1
            if (lines or entries) and blanks >= 3:
                break
            continue
        blanks = 0
        side = None
        if amount := _cell_amount(get(row, "amount")):
            signed = amount.signed
        elif amount := _cell_amount(get(row, "debit")):
            signed, side = -amount.value, False
        elif amount := _cell_amount(get(row, "credit")):
            signed, side = amount.value, True
        else:
            continue
        op_name = _cell_text(row[op_col]) if op_col is not None and op_col < len(row) else ""
        detail = " ".join(_cell_text(row[j]) for j in detail_cols if j < len(row) and _cell_text(row[j]))
        if is_card_statement:
            text = " ".join(filter(None, [op_name, detail]))
            installment = _cell_text(get(row, "installment"))
            entries.append(card.CardEntry(date=day, description=text, amount=amount, side=side,
                                          installment_words=installment.split(), raw=text,
                                          summary=card.is_summary(text)))
        else:
            lines.append(ParsedLine(date=day, description=describe_account(op_name or detail, detail if op_name else ""),
                                    amount=signed, raw_text=f"{op_name} {detail}".strip(),
                                    external_ref=_cell_text(get(row, "ref"))))
            balances.append(_cell_amount(get(row, "balance")))

    if holder := pairs.get("hesap sahibi"):
        result.holder_name = holder[:100]
    printed_closing = None
    if balance := pairs.get("bakiye"):
        if amount := parse_amount(balance.replace(" ", "").replace("TL", "")):
            printed_closing = result.closing_balance = amount.signed
    if (period := pairs.get("tarih araligi")) and len(dates := _dates(period)) >= 2:
        result.period_start, result.period_end = dates[0], dates[1]
    if is_card_statement:
        meta_lines = _text_lines(table[:header_at])
        cut_off = label_date([line.text for line in meta_lines], CUT_OFF, skip=("sonraki", "onceki"))
        if cut_off and not result.period_start:
            result.period_start, result.period_end = card_period(cut_off)
        elif entries and not result.period_start:
            result.period_start, result.period_end = min(e.date for e in entries), max(e.date for e in entries)
        card.finish(result, entries, [], summary.label_values(meta_lines, set()), cut_off)
        if result.check_status == "unknown":
            set_check(result, "unknown", "Excel kart ekstresi toplamla doğrulanamadı; satırları kontrol edin.")
        return result
    result.lines = lines
    if not result.period_start and lines:
        result.period_start, result.period_end = min(r.date for r in lines), max(r.date for r in lines)
    check_balances(result, [b.signed if b else None for b in balances], [abs(r.amount) for r in lines],
                   printed_closing)
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

