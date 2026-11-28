"""
Card statements: transaction rows -> lines, checked against the statement's own summary.

The reader is unsure about a few things on an unknown layout; instead of guessing once, every reasonable
interpretation is built and the one the statement confirms wins (the default one on a tie):
  - which printed sign marks a purchase ("" -> payments carry "+"/"-", or the other way round)
  - amounts on undated lines under a row: a breakdown of that row (Anapara + Faiz + BSMV = row amount, ignored)
    or rows of their own whose date line is missing ("orphans", included only when that makes the totals agree)
  - which summary values belong together (summary.readings)
Checks: previous + charges - credits = debt (always, when a debt is printed), and, when the summary prints them,
charges and credits separately. A failed check points at the lines whose amount explains the difference.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from . import layout, summary
from .base import ParsedLine, ParsedStatement
from .tokens import Amount, Installment, parse_amount
from .utils import card_period, fold
from .vocabulary import DETAIL_INSTALLMENT, PAYMENT_WORDS, SUMMARY_WORDS

TOLERANCE = Decimal("0.05")
DETAIL_GAP = 14.0  # points: an undated line closer than this under a row belongs to it
OLD_DATE_DAYS = 45  # a non-installment row dated this long before the period is not from this period
LATE_DATE_DAYS = 3


@dataclass
class CardEntry:
    date: date
    description: str
    amount: Amount
    side: bool | None  # True credit / False debit when a debit/credit column says so, None: decided by sign
    installment_words: list[str] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)  # continuation text under the row
    raw: str = ""
    summary: bool = False  # previous balance / total row, not a transaction


@dataclass
class Orphan:
    parent: CardEntry
    amount: Amount
    text: str


@dataclass
class Outcome:
    lines: list[ParsedLine]
    kinds: list[str]  # per line: charge | payment | refund
    checks: list[dict]
    reading: summary.Reading | None
    totals: dict
    used: tuple[int, ...] = ()  # orphans read as rows

    @property
    def orphans_used(self) -> int:
        return len(self.used)


def money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) < TOLERANCE


def _same(a: Decimal, b: Decimal) -> bool:
    """Exact to the cent: pointing at a line needs more than the rounding tolerance of totals."""
    return abs(a - b) < Decimal("0.005")


def is_summary(description: str) -> bool:
    return any(word in fold(description) for word in SUMMARY_WORDS)


# ---------------------------------------------------------------- PDF rows -> entries
def _row_amount(row) -> tuple[Amount, bool | None] | None:
    """(amount, credit?) where credit is decided by a debit/credit column, else None (decided by sign markers)."""
    if found := row.amounts("amount"):
        return found[-1], None
    if found := row.amounts("debit"):
        return found[-1], False
    if found := row.amounts("credit"):
        return found[-1], True
    return None


def pdf_entries(lines, rows, columns) -> tuple[list[CardEntry], list[Orphan]]:
    """Rows with an amount -> entries; undated lines under a row -> its detail text, a breakdown or orphans."""
    money_columns = [c for c in columns if c.role in layout.MONEY_ROLES]
    by_line = {id(r.line): r for r in rows}
    detail: dict[int, tuple[list[str], list[tuple[Amount, str]]]] = {id(r): ([], []) for r in rows}
    current, last_top = None, 0.0
    for line in lines:
        if id(line) in by_line:
            current, last_top = by_line[id(line)], line.top
            continue
        if current is None:
            continue
        if line.page != current.line.page or line.top - last_top > DETAIL_GAP or layout.header_labels(line):
            current = None
            continue
        in_column = [w for w in line.words if parse_amount(w.text) and any(c.holds(w) for c in money_columns)]
        if in_column:
            if is_summary(line.text):
                current = None  # "TOPLAM ..." / "ÖNCEKİ DÖNEM ...": the table's own totals
                continue
            word = in_column[-1]
            label = " ".join(w.text for w in line.words if w is not word and not parse_amount(w.text))
            detail[id(current)][1].append((parse_amount(word.text), label))
        else:
            detail[id(current)][0].append(line.text.strip())
        last_top = line.top

    entries, orphans = [], []
    for row in rows:
        found = _row_amount(row)
        if not found:
            continue
        amount, side = found
        texts, amount_lines = detail[id(row)]
        entry = CardEntry(
            date=row.date, description=row.description, amount=amount, side=side,
            installment_words=list(row.installment_words), detail=texts,
            raw=" ".join([row.raw, *texts, *(label for _, label in amount_lines)]).strip(),
            summary=is_summary(row.description),
        )
        entries.append(entry)
        orphans += [Orphan(entry, a, label) for a, label in amount_lines[_breakdown_length(amount_lines, amount):]]
    return entries, orphans


def _breakdown_length(amount_lines: list[tuple[Amount, str]], parent: Amount) -> int:
    """How many of the amount lines under a row are its breakdown (Anapara + Faiz + BSMV + KKDF = row amount):
    the first lines whose sum is the row amount. The rest may be rows whose date line is missing."""
    total = Decimal(0)
    for n, (amount, _) in enumerate(amount_lines, start=1):
        total += amount.value
        if _close(total, parent.value) and n >= 2:
            return n
    return 0


# ---------------------------------------------------------------- interpretations
def purchase_signs(entries: list[CardEntry]) -> list[str]:
    """Which printed sign marks a purchase, most likely first: decided by the payment rows ("ÖDEMENİZ İÇİN
    TEŞEKKÜRLER" are credits) when they agree, else unmarked purchases first."""
    signed = [e for e in entries if e.side is None and not e.summary]
    present = sorted({e.amount.sign for e in signed if e.amount.sign})
    payment_signs = {e.amount.sign for e in signed if any(w in fold(e.description) for w in PAYMENT_WORDS)}
    first = ""
    if len(payment_signs) == 1 and not next(iter(payment_signs)):
        markers = Counter(e.amount.sign for e in signed if e.amount.sign)
        first = markers.most_common(1)[0][0] if markers else ""  # payments unmarked -> purchases carry the sign
    return [first, *(s for s in ["", *present] if s != first)]


def _installment(entry: CardEntry) -> tuple[str, str]:
    """(installment text, description without installment notes)."""
    inst = Installment()
    for word in entry.installment_words:
        inst.add_token(word)
    inst.read_description(" ".join(entry.installment_words))  # "11.Taksit", plans split over words
    description = inst.read_description(entry.description)
    for text in entry.detail:  # "388.956,61 TL'lik işlemin 20 / 40 taksidi"
        if m := DETAIL_INSTALLMENT.search(fold(text)):
            inst.number = inst.number or int(m.group(1))
            inst.total = inst.total or int(m.group(2))
    return str(inst), description


def _dated(entry_date: date, installment: str, period_start, cut_off) -> tuple[date, tuple | None]:
    """Booking date + flag (code, text, level). Installments of earlier purchases keep the purchase date on the
    statement; they and rows dated long before the period belong to this statement's cut-off date."""
    shown = entry_date.strftime("%d.%m.%Y")
    if period_start and cut_off and entry_date < period_start:
        if installment:
            return cut_off, ("installment_date", f"Taksit: asıl işlem tarihi {shown}; bu ekstrenin kesim "
                                                 "tarihine yazıldı.", "info")
        if entry_date < period_start - timedelta(days=OLD_DATE_DAYS):
            return cut_off, ("old_date", f"Ekstrede {shown} tarihli (dönemden çok önce); kesim tarihine yazıldı. "
                                         "Tarihi kontrol edin.", "warn")
    if cut_off and entry_date > cut_off + timedelta(days=LATE_DATE_DAYS):
        return entry_date, ("date_outside", f"Tarih ({shown}) ekstre döneminin dışında; kontrol edin.", "warn")
    return entry_date, None


def _line(entry_date, description, amount: Amount, credit: bool, installment, raw, flag) -> tuple[ParsedLine, str]:
    from .engine import clean_description

    description = clean_description(description) or "Kart işlemi"
    payment = credit and any(word in fold(description) for word in PAYMENT_WORDS)
    line = ParsedLine(date=entry_date, description=description, amount=amount.value if credit else -amount.value,
                      raw_text=raw, installment=installment, hint="card_payment" if payment else "")
    if flag:
        line.flag(*flag)
    return line, ("payment" if payment else "refund") if credit else "charge"


def build(entries, orphans, sign: str, used: tuple[int, ...], period_start, cut_off) -> list[tuple[ParsedLine, str]]:
    """Lines for one interpretation: `sign` marks purchases, `used` = indexes of the orphans read as rows
    (each placed right after the row it was printed under, with that row's date)."""
    out = []
    for entry in entries:
        if entry.summary:
            continue
        credit = entry.side if entry.side is not None else entry.amount.sign != sign
        installment, description = _installment(entry)
        booked, flag = _dated(entry.date, installment, period_start, cut_off)
        out.append(_line(booked, description, entry.amount, credit, installment, entry.raw, flag))
        for index in used:
            orphan = orphans[index]
            if orphan.parent is entry:
                out.append(_line(booked, orphan.text, orphan.amount, orphan.amount.sign != sign, "", orphan.text,
                                 ("from_detail", "Bu tutar tarihsiz bir satırdan okundu (tarih üstteki işlemden); "
                                                 "ekstre toplamını tutturduğu için eklendi.", "warn")))
    return out


def orphan_options(orphans) -> list[tuple[int, ...]]:
    """None of them, all of them, or a single one (a missed row is usually one row)."""
    if not orphans:
        return [()]
    every = tuple(range(len(orphans)))
    singles = [(i,) for i in every] if 1 < len(orphans) <= 8 else []
    return [(), every, *singles]


def evaluate(built: list[tuple[ParsedLine, str]], reading: summary.Reading | None) -> tuple[list[dict], dict]:
    totals = {kind: sum((abs(l.amount) for l, k in built if k == kind), Decimal(0))
              for kind in ("charge", "payment", "refund")}
    if reading is None:
        return [], totals
    credits = totals["payment"] + totals["refund"]
    net = totals["charge"] - credits
    actual = (reading.previous or 0) + net
    checks = [{"code": "balance", "label": "Önceki borç + harcamalar − ödemeler = dönem borcu",
               "expected": str(reading.debt), "actual": str(actual), "ok": _close(actual, reading.debt)}]
    if reading.charges is not None:  # refunds may be netted into the printed spending
        options = [totals["charge"], totals["charge"] - totals["refund"]]
        value = next((v for v in options if _close(v, reading.charges)), options[0])
        checks.append({"code": "charges", "label": "Dönem harcamaları", "expected": str(reading.charges),
                       "actual": str(value), "ok": _close(value, reading.charges)})
    if reading.credits is not None:  # ... or left out of the printed payments
        options = [credits, totals["payment"]]
        value = next((v for v in options if _close(v, reading.credits)), options[0])
        checks.append({"code": "credits", "label": "Dönem ödemeleri", "expected": str(reading.credits),
                       "actual": str(value), "ok": _close(value, reading.credits)})
    return checks, totals


def choose(entries, orphans, readings, period_start, cut_off) -> Outcome:
    """Every interpretation x every summary reading; the one the statement confirms best wins, the most likely
    interpretation (first) on a tie."""
    hypotheses = [(sign, used) for sign in purchase_signs(entries) for used in orphan_options(orphans)]
    best, best_key = None, None
    for index, (sign, used) in enumerate(hypotheses):
        built = build(entries, orphans, sign, used, period_start, cut_off)
        for reading in readings or [None]:
            checks, totals = evaluate(built, reading)
            passed = sum(c["ok"] for c in checks)
            key = (bool(checks) and passed == len(checks), bool(checks) and checks[0]["ok"], passed,
                   reading.rank if reading else 0, -index)
            if best_key is None or key > best_key:
                best_key = key
                best = Outcome([line for line, _ in built], [kind for _, kind in built], checks, reading, totals,
                               used)
    return best


# ---------------------------------------------------------------- result
def _point_at(outcome: Outcome, orphans, difference: Decimal, kinds: set[str]) -> list[str]:
    """Flag the lines whose amount explains `difference`; returns hints for the message."""
    target = abs(difference)
    hints = []
    for line, kind in zip(outcome.lines, outcome.kinds):
        if kind not in kinds:
            continue
        if _same(abs(line.amount), target):
            line.flag("suspect", f"Ekstre toplamındaki fark ({money(target)} TL) bu satırın tutarına eşit: fazladan, "
                                 "eksik ya da yanlış okunmuş olabilir.")
            hints.append("same")
        elif _same(2 * abs(line.amount), target):
            line.flag("suspect_sign", f"Ekstre toplamındaki fark ({money(target)} TL) bu satırın iki katı: gider/gelir "
                                      "yönü ters okunmuş olabilir.")
            hints.append("sign")
    for index, orphan in enumerate(orphans):
        if index not in outcome.used and _same(orphan.amount.value, target):
            hints.append(f"orphan:{orphan.text[:40]}")
    return hints


def _message_hints(hints: list[str]) -> str:
    orphan = next((h for h in hints if h.startswith("orphan:")), None)
    if orphan:
        return f" Fark, ekstredeki tarihsiz bir tutarla aynı ('{orphan[7:]}'): okunmamış olabilir."
    if hints:
        return " Farkı açıklayabilecek satırlar işaretlendi."
    return ""


def finish(result: ParsedStatement, entries, orphans, values, cut_off, row_previous=None):
    """Choose the interpretation, set lines, checks and the check message."""
    readings = summary.readings(values, row_previous)
    outcome = choose(entries, orphans, readings, result.period_start, cut_off)
    result.lines, result.checks = outcome.lines, outcome.checks
    reading = outcome.reading
    if reading is None:
        result.check_status = "unknown"
        result.check_message = "Ekstrede dönem borcu bulunamadı; satırları kontrol edin."
        return
    by_code = {c["code"]: c for c in outcome.checks}
    if all(c["ok"] for c in outcome.checks):
        parts = [f"dönem borcu {money(reading.debt)} TL"]
        if "charges" in by_code:
            parts.append(f"harcamalar {money(reading.charges)} TL")
        if "credits" in by_code:
            parts.append(f"ödemeler {money(reading.credits)} TL")
        added = f" Tarihsiz satırlardan {outcome.orphans_used} tutar eklendi." if outcome.orphans_used else ""
        result.check_status = "ok"
        result.check_message = f"Ekstre toplamıyla doğrulandı ({', '.join(parts)}).{added}"[:255]
        return
    result.check_status = "mismatch"
    balance = by_code["balance"]
    if not balance["ok"]:
        difference = Decimal(balance["expected"]) - Decimal(balance["actual"])
        hints = _point_at(outcome, orphans, difference, {"charge", "payment", "refund"})
        message = f"Okunan satırlar ekstre toplamıyla tutmuyor (fark {money(difference)} TL).{_message_hints(hints)}"
    else:
        failed = next(c for c in outcome.checks if not c["ok"])
        difference = Decimal(failed["expected"]) - Decimal(failed["actual"])
        kinds = {"charge"} if failed["code"] == "charges" else {"payment", "refund"}
        hints = _point_at(outcome, orphans, difference, kinds | {"charge", "payment", "refund"})
        what = "harcamalar" if failed["code"] == "charges" else "ödemeler"
        message = (f"Dönem borcu tutuyor ama okunan {what} ({money(Decimal(failed['actual']))} TL) ekstredekinden "
                   f"({money(Decimal(failed['expected']))} TL) farklı: bir satırın gider/gelir yönü hatalı "
                   f"olabilir.{_message_hints(hints)}")
    result.check_message = (message + " Satırları kontrol edin, gerekirse ekstreyi bize bildirin.")[:255]


def read_pdf(result: ParsedStatement, lines, rows, columns, text_lines: list[str]):
    from .engine import label_date
    from .vocabulary import CUT_OFF, PREVIOUS_CUT_OFF

    cut_off = label_date(text_lines, CUT_OFF, skip=("sonraki", "onceki"))
    if cut_off:
        result.period_start, result.period_end = card_period(cut_off)
        if (previous := label_date(text_lines, PREVIOUS_CUT_OFF, skip=())) and previous < cut_off:
            result.period_start = previous + timedelta(days=1)
    entries, orphans = pdf_entries(lines, rows, columns)
    row_previous = next((e.amount.value for e in entries if e.summary
                         and any(w in fold(e.description) for w in ("onceki", "devir"))), None)
    values = summary.read(lines, {id(r.line) for r in rows})
    finish(result, entries, orphans, values, cut_off, row_previous)
