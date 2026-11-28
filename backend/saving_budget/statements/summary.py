"""
Card statement summary: the totals a statement prints about itself, read without per-bank code.

Three shapes cover the banks seen so far:
  - label : amount on one line      "Dönem Borcunuz : 15.166,39 TL", "Dönem İçi Ödemeler :+20.298,72 TL"
  - grid / equation                 labels on 1-4 lines, the amounts on the line below, matched by position:
                                    "Önceki Bakiye  Dönem Harcamaları  Faiz ve Ücretler  Ödemeleriniz  Dönem Borcunuz"
                                    "6.104,49 TL  +  39.278,45 TL  +  7,74 TL  -  6.104,49 TL  =  39.286,19 TL"
  - a summary row in the table      "ÖNCEKİ DÖNEM HESAP ÖZETİ BORCU 10.149,36"
Every value is a candidate; `readings()` keeps the combinations that agree with themselves
(previous + charges - credits = debt), so a wrong candidate (a per-card subtotal, a fee schedule) drops out.
"""

from dataclasses import dataclass
from decimal import Decimal
from itertools import product

from .layout import Line
from .tokens import parse_amount
from .utils import fold
from .vocabulary import FILLER_WORDS, SUMMARY_IGNORE, SUMMARY_OPERATORS, SUMMARY_ROLES

TOLERANCE = Decimal("0.05")
LABEL_WORDS = 7  # words before an amount that can be its label
GRID_LABEL_SPAN = 45.0  # points above a grid's amount line where its labels are printed
GRID_LABEL_DISTANCE = 90.0  # a label word belongs to the amount whose center is nearest, within this


@dataclass
class SummaryValue:
    role: str  # previous | debt | charges | cash | fees | credits
    value: Decimal  # absolute value
    label: str
    source: str  # "label" | "grid" | "row"
    group: int | None = None  # grid id: the values of one grid are the parts of one equation


@dataclass
class Reading:
    """One consistent interpretation of the summary (or only a debt + previous, when nothing agrees)."""
    debt: Decimal
    previous: Decimal | None
    charges: Decimal | None  # spending + cash advance + fees (None: not printed / not consistent)
    credits: Decimal | None
    kind: str  # "full" (previous + charges - credits = debt) | "balance" (only debt and maybe previous)
    source: str

    @property
    def rank(self) -> int:
        return {"full": 3, "balance": 1}[self.kind] + (1 if self.source == "grid" else 0)


def classify(label: str) -> str | None:
    folded = f" {fold(label)} "
    if any(word in folded for word in SUMMARY_IGNORE):
        return None
    for role, phrases in SUMMARY_ROLES:
        if any(p in folded for p in phrases):
            return role
    return None


def _amount(text: str):
    return parse_amount(text.strip(":"))


def _operator(text: str) -> bool:
    return text in SUMMARY_OPERATORS


def _is_amount_line(line: Line) -> bool:
    """A grid's value line: ≥3 amounts and nothing else but currency words / operators."""
    amounts = [w for w in line.words if _amount(w.text)]
    others = [w for w in line.words if not _amount(w.text) and fold(w.text) not in ("tl", "try", "₺")
              and not _operator(w.text)]
    return len(amounts) >= 3 and len(others) <= 1


def label_values(lines: list[Line], skip: set[int]) -> list[SummaryValue]:
    """'label : amount' pairs on lines that are not transaction rows (skip: ids of row lines) or grid lines."""
    out = []
    for line in lines:
        if id(line) in skip or _is_amount_line(line):
            continue
        words = line.words
        start = 0
        for i, w in enumerate(words):
            amount = _amount(w.text)
            if not amount:
                continue
            label_words = []
            for j in range(i - 1, start - 1, -1):
                # the amount may be right-aligned far from its label; inside the label a wide gap means
                # another column's text
                if (j < i - 1 and words[j + 1].x0 - words[j].x1 > 40) or len(label_words) >= LABEL_WORDS:
                    break
                label_words.insert(0, words[j].text)
            start = i + 1
            label = " ".join(t for t in label_words if fold(t) not in ("tl", "try", ":"))
            if (role := classify(label)) is not None:
                out.append(SummaryValue(role, amount.value, label, "label"))
    return out


def grid_values(lines: list[Line]) -> list[SummaryValue]:
    out = []
    for index, line in enumerate(lines):
        if not _is_amount_line(line):
            continue
        amounts = [w for w in line.words if _amount(w.text)]
        centers = [(w.x0 + w.x1) / 2 for w in amounts]
        labels: list[list] = [[] for _ in amounts]
        last_top = line.top
        for above in reversed(lines[max(0, index - 6):index]):
            if above.page != line.page or line.top - above.top > GRID_LABEL_SPAN or last_top - above.top > 20:
                break
            texts = [w.text for w in above.words]
            if any(_amount(t) for t in texts) or _has_date(texts) or _sentence(above):
                break  # another table / a sentence: not this grid's labels
            for phrase in _phrases(above):
                center = (phrase[0].x0 + phrase[-1].x1) / 2
                nearest = min(range(len(centers)), key=lambda k: abs(centers[k] - center))
                if abs(centers[nearest] - center) <= GRID_LABEL_DISTANCE:
                    labels[nearest] += phrase
            last_top = above.top
        if not any(labels):
            continue
        whole = " ".join(w.text for ws in labels for w in ws)
        if classify(whole) is None and any(word in fold(whole) for word in ("puan", "bonus")):
            continue  # points / bonus grid
        for amount_word, words in zip(amounts, labels):
            text = " ".join(w.text for w in sorted(words, key=lambda w: (w.top, w.x0)) if not _operator(w.text))
            if (role := classify(text)) is not None:
                out.append(SummaryValue(role, _amount(amount_word.text).value, text, "grid", group=index))
    return out


def _phrases(line: Line, gap=5.0) -> list[list]:
    """A label line cut into headings: words closer than `gap` belong together; operators and filler split them.
    'Önceki Bakiye  Dönem Harcamaları  Faiz ve Ücretler' -> three headings (one per grid column)."""
    out, current, last = [], [], None
    for w in line.words:
        if _operator(w.text) or fold(w.text) in FILLER_WORDS:
            if current:
                out.append(current)
            current, last = [], None
            continue
        if last is not None and w.x0 - last.x1 > gap:
            out.append(current)
            current = []
        current.append(w)
        last = w
    if current:
        out.append(current)
    return out


def _sentence(line: Line) -> bool:
    """Running text: 6+ words without a column gap or an operator between them, with sentence punctuation or
    numbers in it (grid labels are short headings: 'Önceki Bakiye Dönem Harcamaları ... Min. Ödeme Tutarınız')."""
    run: list[str] = []
    for prev, w in zip([None, *line.words], line.words):
        if _operator(w.text) or (prev is not None and w.x0 - prev.x1 > 15):
            run = []
        if _operator(w.text):
            continue
        run.append(w.text)
        if len(run) >= 6 and any(c in t for t in run for c in ',"\'0123456789!?'):
            return True
    return False


def _has_date(texts: list[str]) -> bool:
    from .tokens import find_date

    return find_date(" ".join(texts)) is not None


def read(lines: list[Line], row_line_ids: set[int]) -> list[SummaryValue]:
    return grid_values(lines) + label_values(lines, row_line_ids)


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) < TOLERANCE


def _unique(values) -> list[Decimal]:
    out = []
    for v in values:
        if not any(_close(v, x) for x in out):
            out.append(v)
    return out[:8]


def readings(values: list[SummaryValue], row_previous: Decimal | None = None) -> list[Reading]:
    """Consistent interpretations, best first: grids, then label combinations, then debt + previous only."""
    found: list[Reading] = []

    def add(reading: Reading):
        if not any(_close(r.debt, reading.debt) and r.previous == reading.previous and r.charges == reading.charges
                   and r.credits == reading.credits for r in found):
            found.append(reading)

    for group in sorted({v.group for v in values if v.group is not None}):
        parts = [v for v in values if v.group == group]
        by_role = {role: [v.value for v in parts if v.role == role] for role, _ in SUMMARY_ROLES}
        if len(by_role["debt"]) != 1 or len(by_role["previous"]) > 1:
            continue
        debt = by_role["debt"][0]
        previous = by_role["previous"][0] if by_role["previous"] else None
        charge_parts = by_role["charges"] + by_role["cash"] + by_role["fees"]
        charges = sum(charge_parts, Decimal(0)) if charge_parts else None
        credits = sum(by_role["credits"], Decimal(0)) if by_role["credits"] else None
        if charges is not None and credits is not None and _close((previous or 0) + charges - credits, debt):
            add(Reading(debt, previous, charges, credits, "full", "grid"))

    pick = {role: _unique(v.value for v in values if v.role == role and v.group is None) for role, _ in SUMMARY_ROLES}
    grid_pick = {role: _unique(v.value for v in values if v.role == role) for role, _ in SUMMARY_ROLES}
    debts = _unique(pick["debt"] + grid_pick["debt"])
    previous_values = _unique(pick["previous"] + grid_pick["previous"] + ([row_previous] if row_previous else []))
    for debt, previous, credits in product(debts, [*previous_values, None], pick["credits"]):
        # each part is optional: a bank may print only spending, or spending + fees ...
        for charges, cash, fees in product([*pick["charges"], None], [*pick["cash"], None], [*pick["fees"], None]):
            parts = [p for p in (charges, cash, fees) if p is not None]
            if parts and _close((previous or 0) + sum(parts) - credits, debt):
                add(Reading(debt, previous, sum(parts, Decimal(0)), credits, "full", "label"))
    for debt, previous in product(debts, previous_values + [None]):
        add(Reading(debt, previous, None, None, "balance", "label"))
    return sorted(found, key=lambda r: -r.rank)
