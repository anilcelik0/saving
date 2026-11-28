"""
PDF layout: words with positions -> visual lines -> transaction table.

Columns are found from the data itself: amounts of rows that start with a date are right-aligned, so their right
edges cluster per column. Header lines ("Tarih ... Tutar ... Bakiye") give the clusters a role when they overlap;
unlabeled clusters get one from the engine (e.g. by checking a running balance). Numbers that do not fall into a
column (e.g. "(İşlem tutarı: 485,01 TL)" inside a description) stay part of the description.
"""

import re
from dataclasses import dataclass, field
import datetime as dt

import pdfplumber

from .cid import decode, learn_mapping
from .tokens import CURRENCY_WORDS, SIGN_WORDS, Amount, is_time, leading_date, parse_amount
from .utils import fold
from .vocabulary import ROLE_PHRASES

LINE_TOLERANCE = 3.0  # points: words whose tops differ less belong to the same visual line
COLUMN_TOLERANCE = 6.0  # points: right edges closer than this belong to the same numeric column
LABEL_SLACK = 12.0  # header label span is widened by this much when matching data columns

MONEY_ROLES = {"amount", "debit", "credit", "balance"}
UNUSED_VALUE_ROLES = {"bonus", "original", "time"} | MONEY_ROLES
# installment notes that may sit under another header: "11.Taksit", "3.", "1.799,88x12=...", "2x1.136,50", "2/6"
INSTALLMENT_HINT = re.compile(r"taksit|^\d{1,2}\.$|x\d{1,2}=|^\d{1,2}x[\d.,]+$|^\d{1,2}/\d{1,2}$")


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    page: int


@dataclass
class Line:
    words: list[Word]
    page: int
    top: float

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Label:
    role: str
    x0: float
    x1: float
    text: str


@dataclass
class Column:
    anchor: str  # "x1" right-aligned, "x0" left-aligned, "xc" centered
    pos: float  # mean anchor position
    x0: float  # span of the values
    x1: float
    count: int
    role: str = ""
    labeled: bool = False

    def holds(self, word: "Word") -> bool:
        return abs(_anchor(word, self.anchor) - self.pos) <= COLUMN_TOLERANCE


def _anchor(word: "Word", anchor: str) -> float:
    return word.x1 if anchor == "x1" else word.x0 if anchor == "x0" else (word.x0 + word.x1) / 2


@dataclass
class Cell:
    amount: Amount
    column: Column
    word: Word


@dataclass
class Row:
    date: dt.date
    line: Line
    words: list[Word]  # after the date (and time)
    labels: list[Label] = field(default_factory=list)  # header in effect for this row
    cells: list[Cell] = field(default_factory=list)
    installment_words: list[str] = field(default_factory=list)
    ref: str = ""
    description_words: list[str] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)  # continuation lines (account statements)

    def amounts(self, role: str) -> list[Amount]:
        return [c.amount for c in self.cells if c.column.role == role]

    @property
    def description(self) -> str:
        return " ".join(self.description_words)

    @property
    def raw(self) -> str:
        return " ".join([self.line.text, *self.detail])


# ---------------------------------------------------------------- words -> lines
def extract_pages(path: str) -> list[list[dict]]:
    """The reader's whole input from a PDF: words per page as {"text", "x0", "x1", "top"}, "(cid:N)" glyphs decoded.
    Sample fixtures (samples.py) store exactly this, so a masked sample reads like the original file."""
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_words(keep_blank_chars=False, use_text_flow=False) for page in pdf.pages]
    text = " ".join(w["text"] for words in pages for w in words)
    mapping = learn_mapping(text) if "(cid:" in text else {}
    return [
        [{"text": decode(w["text"], mapping) if mapping else w["text"],
          "x0": float(w["x0"]), "x1": float(w["x1"]), "top": float(w["top"])} for w in words]
        for words in pages
    ]


def read_lines(path: str) -> list[Line]:
    return lines_from_pages(extract_pages(path))


def lines_from_pages(pages: list[list[dict]]) -> list[Line]:
    lines = []
    for page_no, words in enumerate(pages):
        current: list[Word] = []
        for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
            word = Word(w["text"], w["x0"], w["x1"], w["top"], page_no)
            if current and abs(word.top - current[0].top) > LINE_TOLERANCE:
                lines.append(_line(current, page_no))
                current = []
            current.append(word)
        if current:
            lines.append(_line(current, page_no))
    return lines


def _line(words: list[Word], page: int) -> Line:
    words = sorted(words, key=lambda w: w.x0)
    return Line(words=words, page=page, top=words[0].top)


# ---------------------------------------------------------------- header labels
def _key(word: str) -> str:
    """Folded header word without punctuation; a glued currency note is dropped ("Tutar(TL)" -> "tutar")."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\((tl|try|₺)\)", "", fold(word)))


def header_labels(line: Line) -> list[Label]:
    """Column labels of a table header line, or [] if the line is not a header."""
    keys = [_key(w.text) for w in line.words]
    labels, i = [], 0
    while i < len(keys):
        for phrase, role in ROLE_PHRASES:
            if tuple(keys[i:i + len(phrase)]) == phrase:
                words = line.words[i:i + len(phrase)]
                labels.append(Label(role, words[0].x0, words[-1].x1, " ".join(w.text for w in words)))
                i += len(phrase)
                break
        else:
            if labels and keys[i] in ("tl", "try", "") and line.words[i].x0 - labels[-1].x1 < 8:
                labels[-1].x1 = line.words[i].x1  # "(TL)", "/" belong to the label before
            i += 1
    roles = {label.role for label in labels}
    if "date" in roles and roles & (MONEY_ROLES | {"description"}) and len(labels) >= 3:
        return labels
    return []


# ---------------------------------------------------------------- table rows
def _merge_signs(words: list[Word]) -> list[Word]:
    """'-' or '+' printed as its own word right before an amount belongs to the amount."""
    out = []
    for w in words:
        if out and out[-1].text in SIGN_WORDS and w.x0 - out[-1].x1 < 8 and parse_amount(w.text):
            sign = out.pop()
            w = Word(sign.text + w.text, sign.x0, w.x1, w.top, w.page)
        out.append(w)
    return out


def table_rows(lines: list[Line]) -> tuple[list[Row], list[Column], bool]:
    """
    Rows starting with a date + numeric columns, roles taken from header labels where they overlap.
    Unlabeled columns keep role "" until the engine resolves them; then call assign(). bool: a header was found.
    """
    rows, labels_by_page = [], {}
    for line in lines:
        if labels := header_labels(line):
            labels_by_page.setdefault(line.page, []).append((line.top, labels))
            continue
        texts = [w.text for w in line.words]
        found = leading_date(texts)
        if not found:
            continue
        used = found[1]
        while used < len(texts) and is_time(texts[used]):
            used += 1
        rows.append(Row(date=found[0], line=line, words=_merge_signs(line.words[used:])))

    columns = _columns(rows)
    first = next((lab for page in sorted(labels_by_page) for _, lab in labels_by_page[page]), [])
    current = first
    for row in rows:
        above = [lab for top, lab in labels_by_page.get(row.line.page, []) if top < row.line.top]
        if above:
            current = above[-1]  # header repeated on this page
        row.labels = current
        _label_columns(columns, current)
    return rows, columns, bool(labels_by_page)


def assign(rows: list[Row], columns: list[Column]):
    """Split each row into amount cells (resolved columns), installment info, reference and description words."""
    for row in rows:
        row.cells, row.installment_words, row.description_words, row.ref = [], [], [], ""
        _assign(row, columns, row.labels)


def _under_unused(w: Word, labels: list[Label]) -> bool:
    return any(lab.role in UNUSED_VALUE_ROLES and _overlap(w.x0, w.x1, lab.x0 - 4, lab.x1 + 4) > 0 for lab in labels)


def column_amounts(row: Row, column: Column) -> list[Amount]:
    return [a for w in row.words if (a := parse_amount(w.text)) and column.holds(w)]


def _columns(rows: list[Row]) -> list[Column]:
    """
    Amount clusters by alignment; a column needs ≥2 values and ≥15% of the rows. Right-aligned is the norm;
    left-aligned / centered layouts are tried too and the alignment covering most amounts wins.
    """
    words = [w for row in rows for w in row.words if parse_amount(w.text)]
    minimum = max(2, round(len(rows) * 0.15))
    best: list[Column] = []
    for anchor in ("x1", "x0", "xc"):
        clusters: list[list[Word]] = []
        for w in sorted(words, key=lambda w: _anchor(w, anchor)):
            if clusters and _anchor(w, anchor) - _anchor(clusters[-1][-1], anchor) <= COLUMN_TOLERANCE:
                clusters[-1].append(w)
            else:
                clusters.append([w])
        columns = [
            Column(anchor=anchor, pos=sum(_anchor(w, anchor) for w in c) / len(c), x0=min(w.x0 for w in c),
                   x1=max(w.x1 for w in c), count=len(c))
            for c in clusters if len(c) >= minimum
        ]
        if sum(c.count for c in columns) > sum(c.count for c in best):
            best = columns
    return best


def _overlap(a0, a1, b0, b1) -> float:
    return min(a1, b1) - max(a0, b0)


def _label_columns(columns: list[Column], labels: list[Label]):
    for column in columns:
        if column.labeled:
            continue
        best = max(
            (lab for lab in labels if lab.role in MONEY_ROLES | {"bonus", "installment", "original"}),
            key=lambda lab: _overlap(column.x0, column.x1, lab.x0 - LABEL_SLACK, lab.x1 + LABEL_SLACK),
            default=None,
        )
        if best and _overlap(column.x0, column.x1, best.x0 - LABEL_SLACK, best.x1 + LABEL_SLACK) > 0:
            column.role, column.labeled = best.role, True


def _assign(row: Row, columns: list[Column], labels: list[Label]):
    installment = [lab for lab in labels if lab.role == "installment"]
    refs = [lab for lab in labels if lab.role == "ref"]
    for w in row.words:
        amount = parse_amount(w.text)
        column = next((c for c in columns if amount and c.role and c.holds(w)), None)
        if column and column.role not in ("installment", "original"):
            row.cells.append(Cell(amount, column, w))
        elif any(_overlap(w.x0, w.x1, lab.x0 - 4, lab.x1 + 4) > 0 for lab in installment) or (
                INSTALLMENT_HINT.search(fold(w.text)) and _under_unused(w, labels)):
            row.installment_words.append(w.text)
        elif any(_overlap(w.x0, w.x1, lab.x0 - 4, lab.x1 + 4) > 0 for lab in refs) and w.text.isdigit():
            row.ref = w.text
        elif fold(w.text) in CURRENCY_WORDS or w.text in ("*", "**") or re.fullmatch(r"b+o+s+l+u+k+", fold(w.text)):
            continue  # currency next to an amount, reward marker, layout filler "bosluk"
        elif _under_unused(w, labels):
            continue  # value under a column we do not use (points, original currency...): not description text
        else:
            row.description_words.append(w.text)

