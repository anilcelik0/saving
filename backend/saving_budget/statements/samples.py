"""
Sample set for the statement engine: masked fixtures + expected results, checked by `check_statements`.

A fixture is the engine's input (PDF words with positions, or Excel cell values) with personal data masked, so the
same statement can be re-read after every engine change without keeping the real file. Masking keeps positions,
amounts, dates and table labels (what the engine reads) and replaces:
  - names: the holder (engine's own detection, "Sn./Sayın <NAME>"), transfer counterparties, words given by hand
    -> consistent pseudonyms ("AD1"), so own-account transfer detection still works
  - addresses: the block under the addressee name and runs with address words (mah., sk., cad., no:, blok...)
  - numbers: card numbers, IBANs, customer/account/TC numbers, phone numbers -> digits replaced by 0
  - e-mail addresses
The command prints what was masked and whether the fixture still reads exactly like the original; the fixture
should still be reviewed once (`--review`) before it is kept. Fixtures stay out of git (statement_samples/).
"""

import difflib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .base import ParsedStatement
from .engine import HOLDER, INCOMING, OUTGOING, find_header
from .layout import LINE_TOLERANCE
from .profiles import BANK_PHRASES
from .registry import parse_input, read_input
from .tokens import leading_date, parse_amount
from .utils import fold

FIXTURE_VERSION = 1
ADDRESS_WORDS = {
    "mah", "mah.", "mahallesi", "mh.", "sk", "sk.", "sok", "sok.", "sokak", "sokagi", "cad", "cad.", "cd.", "cadde",
    "caddesi", "bulvar", "bulvari", "blv", "blv.", "apt", "apt.", "apartmani", "daire", "kapi", "blok", "sitesi",
}
# a province name in the text outside the rows marks an address (district / city line)
PROVINCES = set("""
adana adiyaman afyonkarahisar afyon agri amasya ankara antalya artvin aydin balikesir bilecik bingol bitlis bolu burdur
bursa canakkale cankiri corum denizli diyarbakir edirne elazig erzincan erzurum eskisehir gaziantep giresun gumushane
hakkari hatay isparta mersin icel istanbul izmir kars kastamonu kayseri kirklareli kirsehir kocaeli konya kutahya
malatya manisa kahramanmaras maras mardin mugla mus nevsehir nigde ordu rize sakarya samsun siirt sinop sivas tekirdag
tokat trabzon tunceli sanliurfa urfa usak van yozgat zonguldak aksaray bayburt karaman kirikkale batman sirnak bartin
ardahan igdir yalova karabuk kilis osmaniye duzce
""".split())
NAME_PREFIXES = {"sn", "sn.", "sayin", "sayın"}
NAME_LABELS = re.compile(r"^(hesap sahibi|ad[ıi]? ?soyad[ıi]?|müşteri ad[ıi]|kart sahibi|kart hamili)\s*:?$", re.I)
# words a captured name may contain that are not personal (bank, legal forms, transfer boilerplate)
NOT_NAME = {
    "a.s.", "a.ş.", "as", "t.a.o.", "bankasi", "bank", "banka", "hesabina", "hesabindan", "giden", "gelen", "tl",
    "fast", "eft", "havale", "ltd", "sti", "ve", "tic", "san",
}
# never masked: table / summary label words and bank names (the engine recognizes the bank from them)
STOP_ADDRESS_WORDS = {"tarih", "tarihi", "borc", "borcu", "limit", "limiti", "odeme", "donem", "hesap", "kart", "toplam",
                      "bakiye", "tutar", "tutari", "islem", "faiz", "puan", "musteri"} | {
    word for phrase, _ in BANK_PHRASES for word in phrase.split()} | {"bankasi", "bank", "vakiflar"}
CARD_GROUP = re.compile(r"^:?[\d*Xx]{4}$")
IBAN_START = re.compile(r"^TR\d{2}", re.I)
EMAIL = re.compile(r"\S+@\S+")


# ---------------------------------------------------------------- masking helpers
INSTALLMENT_TOKEN = re.compile(r"\dx[\d.,]+|[\d.,]+x\d{1,2}=|^\d{1,2}/\d{1,2}$")


def _digits(text: str) -> int:
    return sum(c.isdigit() for c in text)


def _keeps(text: str) -> bool:
    """Words the engine needs as they are: amounts, dates, installment notes ("1x581.50", "1.799,88x12=...")."""
    stripped = text.strip(":")
    return bool(parse_amount(stripped) or leading_date([stripped]) or INSTALLMENT_TOKEN.search(fold(stripped)))


def _zero(text: str) -> str:
    return re.sub(r"\d", "0", text)


def _cross(text: str) -> str:
    return re.sub(r"[^\W\d_]", "X", _zero(text))


BANK_WORDS = {word for phrase, _ in BANK_PHRASES for word in phrase.split() if len(word) >= 4}


def _label_word(text: str) -> bool:
    """Never crossed out: table / summary labels, bank names and web addresses (not personal)."""
    folded = fold(text).strip(":.")
    return folded in STOP_ADDRESS_WORDS or "www." in folded or ".com" in folded or \
        any(bank in folded for bank in BANK_WORDS)


def _date_words(texts: list[str]) -> set[int]:
    """Indexes of words that form a date ("28 Ekim 2025" is three words)."""
    protected, i = set(), 0
    while i < len(texts):
        if found := leading_date(texts[i:i + 3]):
            protected |= set(range(i, i + found[1]))
            i += found[1]
        else:
            i += 1
    return protected


class Masker:
    def __init__(self, extra_names=()):
        self.pseudonyms: dict[str, str] = {}
        self.counts = {"name": 0, "address": 0, "number": 0, "email": 0}
        for word in extra_names:
            self.add_name(word)

    def add_name(self, word: str, min_len=3):
        """min_len 2 for the holder's own name (PDFs split words: "ÇELİK" -> "ÇE" "LİK")."""
        key = fold(word).strip(".,:;()")
        if len(key) >= min_len and key.isalpha() and key not in NOT_NAME and not _label_word(key) \
                and key not in self.pseudonyms:
            self.pseudonyms[key] = f"AD{len(self.pseudonyms) + 1}"

    def add_names(self, text: str, min_len=2):
        for word in text.split():
            self.add_name(word, min_len)

    def add_counterparty(self, captured: str):
        """Transfer text "A.Ş. ... AD SOYAD hesabına giden": the name is the last words before "hesabına"."""
        words = [w for w in re.sub(r"[\d.,()/]+", " ", captured).split() if w.isalpha()]
        for word in words[-4:]:
            self.add_name(word)

    def name(self, text: str) -> str | None:
        key = fold(text).strip(".,:;()")
        if key in self.pseudonyms:
            self.counts["name"] += 1
            return self.pseudonyms[key]
        return None

    def token(self, text: str) -> str:
        """Single-word rules: e-mail, names, long numbers / card fragments / IBAN start."""
        if EMAIL.fullmatch(text):
            self.counts["email"] += 1
            return "x@x"
        if (pseudonym := self.name(text)) is not None:
            return pseudonym
        if _keeps(text):
            return text
        if _digits(text) >= 6 or ("*" in text and _digits(text) >= 2) or IBAN_START.match(text):
            self.counts["number"] += 1
            return _zero(text)
        return text

    def words(self, texts: list[str], meta: bool) -> list[str]:
        """A line's words: token rules + runs (card number groups, IBAN groups, phone numbers, addresses)."""
        protected = _date_words(texts)
        out = [t if i in protected else self.token(t) for i, t in enumerate(texts)]

        def free(k):
            return k < len(out) and k not in protected and not _keeps(out[k])

        i = 0
        while i < len(out):  # card number "5269 11** **** 7112" / IBAN "TR05 0006 ..." / phone "0532 123 45 67"
            j = i
            while free(j) and (CARD_GROUP.match(out[j]) or (j == i and IBAN_START.match(texts[j]))):
                j += 1
            k = i
            while free(k) and out[k].isdigit():
                k += 1
            if j - i >= 3 or (k - i >= 2 and sum(_digits(t) for t in out[i:k]) >= 10):
                end = max(j, k)
                out[i:end] = [_zero(t) for t in out[i:end]]
                self.counts["number"] += 1
                i = end
            else:
                i += 1
        if meta and any(fold(t) in ADDRESS_WORDS for t in out):
            self.counts["address"] += 1
            out = [t if i in protected or _keeps(t) or _label_word(t) else _cross(t) for i, t in enumerate(out)]
        return out


# ---------------------------------------------------------------- PDF fixtures
def _grouped(page: list[dict]) -> list[list[dict]]:
    """Same visual-line grouping as layout.lines_from_pages, on the raw word dicts."""
    lines, current = [], []
    for w in sorted(page, key=lambda w: (w["top"], w["x0"])):
        if current and abs(w["top"] - current[0]["top"]) > LINE_TOLERANCE:
            lines.append(sorted(current, key=lambda w: w["x0"]))
            current = []
        current.append(w)
    if current:
        lines.append(sorted(current, key=lambda w: w["x0"]))
    return lines


def _runs(line: list[dict], gap=15.0) -> list[list[int]]:
    """Word indexes of a line split where the horizontal gap is large (two-column layouts)."""
    runs = []
    for i, w in enumerate(line):
        if runs and w["x0"] - line[runs[-1][-1]]["x1"] <= gap:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def _address_word(text: str) -> bool:
    folded = fold(text).strip(":,")
    if folded in ADDRESS_WORDS:
        return True
    if folded.endswith("."):
        return False  # abbreviation ("Müş." is not the province Muş)
    return any(p in PROVINCES for p in re.split(r"[/\-]", folded) if p)


def _segments(line: list[dict]) -> list[list[int]]:
    """Runs (see _runs) cut at amounts, dates and label words: what is left could be an address or a name.
    'Hesap Kesim Tarihi 28 Ekim 2025 027470 ŞAHİNBEY GAZİANTEP' -> [027470 ŞAHİNBEY GAZİANTEP]."""
    texts = [w["text"] for w in line]
    blocked = _date_words(texts) | {j for j, t in enumerate(texts) if _keeps(t) or _label_word(t)}
    out = []
    for run in _runs(line):
        current = []
        for j in run:
            if j in blocked:
                if current:
                    out.append(current)
                current = []
            else:
                current.append(j)
        if current:
            out.append(current)
    return out


def _address_block(lines, rows, i, x0, x1, masker, find_name_above) -> set[tuple[int, int]]:
    """(line, word) indexes of the address block around line i (x-range x0..x1): free segments of the lines below
    and above that overlap it (one line without one is skipped). The all-caps segment right above the block is the
    addressee's name."""
    marked = set()
    for step, limit in ((1, 5), (-1, 2)):
        last_top, k, misses = lines[i][0]["top"], i, 0
        for _ in range(limit):
            k += step
            if k < 0 or k >= len(lines) or k in rows or abs(lines[k][0]["top"] - last_top) > 16 * (misses + 1):
                break
            line = lines[k]
            hits = [seg for seg in _segments(line)
                    if line[seg[0]]["x0"] <= x1 + 15 and line[seg[-1]]["x1"] >= x0 - 15 and len(seg) <= 8]
            if not hits:
                misses += 1
                if misses > 1:
                    break
                continue
            for seg in hits:
                texts = [line[j]["text"] for j in seg]
                if step == -1 and find_name_above and 2 <= len(texts) <= 4 and \
                        all(t.isalpha() and t.upper() == t for t in texts):
                    for t in texts:
                        masker.add_name(t, 2)
                marked |= {(k, j) for j in seg}
            last_top, misses = line[0]["top"], 0
    return marked


def _labelled_names(line: list[dict], masker: Masker):
    """'Ad soyad Songül Yiğit', 'Hesap Sahibi: AD SOYAD' anywhere on the line (two-column layouts)."""
    texts = [w["text"] for w in line]
    for start in range(len(texts)):
        for width in (3, 2):
            label = " ".join(texts[start:start + width])
            if NAME_LABELS.match(label):
                for t in texts[start + width:start + width + 4]:
                    if not t.strip(":").isalpha() or _label_word(t):
                        break
                    masker.add_name(t.strip(":"), 2)
                break


def mask_pages(pages: list[list[dict]], parsed: ParsedStatement | None, masker: Masker) -> list[list[dict]]:
    if parsed and parsed.holder_name:
        masker.add_names(parsed.holder_name)
    grouped = [_grouped(page) for page in pages]
    text = " ".join(w["text"] for lines in grouped for line in lines for w in line)
    for pattern in (OUTGOING, INCOMING):
        for m in pattern.finditer(text):
            masker.add_counterparty(m.group(1))

    address: list[set[tuple[int, int]]] = []  # per page: (line, word) indexes to cross out
    for lines in grouped:
        rows = {i for i, line in enumerate(lines) if leading_date([w["text"] for w in line][:3])}
        marked = set()
        for i, line in enumerate(lines):
            if i in rows:
                continue
            texts = [w["text"] for w in line]
            if (m := HOLDER.match(" ".join(texts))) is not None:
                masker.add_names(m.group(1))
            _labelled_names(line, masker)
            for k, t in enumerate(texts):
                if fold(t) in NAME_PREFIXES:  # "Sn. AD SOYAD": the address follows under the name
                    name = [j for j in range(k + 1, min(k + 5, len(line)))
                            if texts[j].isalpha() and texts[j].upper() == texts[j]]
                    for j in name:
                        masker.add_name(texts[j], 2)
                    if name:
                        x0 = line[name[0]]["x0"]
                        marked |= _address_block(lines, rows, i, x0, x0 + 250, masker, False)
            for seg in _segments(line):
                if any(_address_word(texts[j]) for j in seg):
                    marked |= {(i, j) for j in seg}
                    marked |= _address_block(lines, rows, i, line[seg[0]]["x0"], line[seg[-1]]["x1"], masker, True)
        address.append(marked)

    masked_pages = []
    for page_no, lines in enumerate(grouped):
        out_page = []
        for i, line in enumerate(lines):
            texts = masker.words([w["text"] for w in line], meta=False)
            crossed = [j for j in range(len(line)) if (i, j) in address[page_no]]
            if crossed:
                masker.counts["address"] += 1
            protected = _date_words([w["text"] for w in line])
            for j in crossed:
                if j not in protected and not _keeps(texts[j]) and not _label_word(texts[j]):
                    texts[j] = _cross(texts[j])
            out_page += [{"text": t, "x0": round(w["x0"], 2), "x1": round(w["x1"], 2), "top": round(w["top"], 2)}
                         for w, t in zip(line, texts)]
        masked_pages.append(out_page)
    return masked_pages


# ---------------------------------------------------------------- Excel fixtures
SENSITIVE_PAIRS = ("hesap sahibi", "ad soyad", "adi soyadi", "musteri adi", "musteri", "adres", "iban", "hesap no",
                   "musteri no", "tc", "tckn", "telefon", "e-posta", "eposta", "kart no", "kart numarasi")


def _encode_cell(value):
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, datetime):
        return {"dt": value.isoformat()}
    if isinstance(value, date):
        return {"d": value.isoformat()}
    if isinstance(value, int):
        return {"i": value}
    if isinstance(value, float):
        return {"f": repr(value)}
    if isinstance(value, Decimal):
        return {"n": str(value)}
    return str(value)


def _decode_cell(value):
    if not isinstance(value, dict):
        return value
    kind, raw = next(iter(value.items()))
    return {"dt": datetime.fromisoformat, "d": date.fromisoformat, "i": int, "f": float, "n": Decimal}[kind](raw)


def mask_table(table: list[list], parsed: ParsedStatement | None, masker: Masker) -> list[list]:
    if parsed and parsed.holder_name:
        masker.add_names(parsed.holder_name)
    header_at, _ = find_header(table)
    header_at = len(table) if header_at is None else header_at
    for row in table:
        for cell in row:
            if isinstance(cell, str):
                for pattern in (OUTGOING, INCOMING):
                    for m in pattern.finditer(cell):
                        masker.add_counterparty(m.group(1))
    out = []
    for index, row in enumerate(table):
        if index == header_at:
            out.append(list(row))  # column labels: never personal, and the engine needs them as they are
            continue
        meta = index < header_at
        new_row, mask_next = [], False
        for cell in row:
            if mask_next and cell not in (None, ""):
                masker.counts["name"] += 1
                number = isinstance(cell, (int, float)) and not isinstance(cell, bool)
                new_row.append(0 if number else _cross(str(cell)))
                mask_next = False
                continue
            if isinstance(cell, str):
                if meta and fold(cell).rstrip(" :") in SENSITIVE_PAIRS:
                    mask_next = True
                    new_row.append(cell)
                    continue
                new_row.append(" ".join(masker.words(cell.split(), meta=meta)))
            elif meta and isinstance(cell, int) and not isinstance(cell, bool) and abs(cell) >= 100000:
                masker.counts["number"] += 1
                new_row.append(0)
            else:
                new_row.append(cell)
        out.append(new_row)
    return out


# ---------------------------------------------------------------- fixture files
def make_fixture(path: str, extra_names=()) -> tuple[dict, ParsedStatement | None, dict]:
    """Original file -> (fixture, parse of the original, masking counts)."""
    ext, data = read_input(path)
    try:
        parsed = parse_input(ext, data)
    except Exception:
        parsed = None
    masker = Masker(extra_names)
    if ext == "pdf":
        masked = mask_pages(data, parsed, masker)
    else:
        masked = [[_encode_cell(c) for c in row] for row in mask_table(data, parsed, masker)]
    fixture = {"version": FIXTURE_VERSION, "type": ext, "created": date.today().isoformat(), "data": masked}
    return fixture, parsed, masker.counts


def fixture_input(fixture: dict):
    if fixture["type"] == "pdf":
        return "pdf", fixture["data"]
    return "xlsx", [[_decode_cell(c) for c in row] for row in fixture["data"]]


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_fixture(fixture: dict) -> ParsedStatement:
    return parse_input(*fixture_input(fixture))


def sample_name(parsed: ParsedStatement | None, ext: str, taken: set[str]) -> str:
    """bank-type-period_end-ext (file names of statements often hold account numbers)."""
    if parsed:
        base = f"{parsed.bank}-{parsed.statement_type}-{parsed.period_end or 'nodate'}-{ext}"
    else:
        base = f"unread-{ext}"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}-{n}", n + 1
    return name


def review_lines(fixture: dict) -> list[str]:
    """Text outside the transaction rows, to check by eye that nothing personal is left."""
    if fixture["type"] == "pdf":
        out = []
        for page in fixture["data"]:
            for line in _grouped(page):
                texts = [w["text"] for w in line]
                if not leading_date(texts[:3]):
                    out.append(" ".join(texts))
        return out
    rows = []
    for row in fixture_input(fixture)[1]:
        if any(isinstance(c, (date, datetime)) for c in row):
            break
        rows.append(" | ".join(str(c) for c in row if c not in (None, "")))
    return rows


# ---------------------------------------------------------------- expected results
def _money(value) -> str | None:
    return None if value is None else str(Decimal(value).quantize(Decimal("0.01")))


def summarize(result: ParsedStatement) -> dict:
    """What check_statements compares: header fields, totals, checks and one text row per line."""
    lines = []
    for line in result.lines:
        flags = ",".join(f["code"] for f in getattr(line, "flags", []) or [])
        lines.append(" | ".join([line.date.isoformat(), _money(line.amount), line.installment or "-",
                                 line.hint or "-", flags or "-", line.description]))
    checks = [f"{c['code']}:{'ok' if c['ok'] else 'fail'}" for c in getattr(result, "checks", []) or []]
    return {
        "bank": result.bank,
        "statement_type": result.statement_type,
        "period": [d.isoformat() if d else None for d in (result.period_start, result.period_end)],
        "closing_balance": _money(result.closing_balance),
        "generic": result.generic,
        "check_status": result.check_status,
        "checks": checks,
        "check_message": result.check_message,
        "line_count": len(result.lines),
        "expense": _money(sum((-line.amount for line in result.lines if line.amount < 0), Decimal(0))),
        "income": _money(sum((line.amount for line in result.lines if line.amount > 0), Decimal(0))),
        "lines": lines,
    }


def compare(expected: dict, actual: dict) -> list[str]:
    """Readable differences (empty: same result)."""
    out = []
    for key in actual:
        if key == "lines" or expected.get(key) == actual[key]:
            continue
        out.append(f"{key}: {expected.get(key)!r} -> {actual[key]!r}")
    diff = list(difflib.unified_diff(expected.get("lines", []), actual["lines"], lineterm="", n=0))
    out += [d for d in diff[2:] if not d.startswith("@@")]
    return out


def input_equal(a: ParsedStatement | None, b: ParsedStatement | None) -> list[str]:
    """Original vs masked fixture: everything but descriptions/holder must read the same."""
    if a is None or b is None:
        return [] if a is b else ["one of them could not be read"]
    sa, sb = summarize(a), summarize(b)
    strip = lambda rows: [" | ".join(r.split(" | ")[:5]) for r in rows]  # noqa: E731
    diffs = [f"{k}: {sa[k]!r} != {sb[k]!r}" for k in sa if k not in ("lines", "check_message") and sa[k] != sb[k]]
    if strip(sa["lines"]) != strip(sb["lines"]):
        diffs.append("lines differ (dates/amounts/installments/hints/flags)")
    return diffs
