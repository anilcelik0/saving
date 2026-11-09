from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


class StatementParseError(Exception):
    """User-facing (Turkish) parse error."""


@dataclass
class ParsedLine:
    date: date
    description: str
    amount: Decimal  # signed from the account owner's view: negative = money out (expense)
    raw_text: str = ""
    external_ref: str = ""  # bank's own transaction number, when available
    installment: str = ""  # "1/3", "kalan 2", "2. taksit" ...
    hint: str = ""  # parser hint for classification, e.g. "card_payment", "investment"


@dataclass
class ParsedStatement:
    bank: str  # parser key, e.g. "vakifbank"
    statement_type: str  # "account" | "card"
    lines: list[ParsedLine] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    closing_balance: Decimal | None = None
    holder_name: str = ""


class BaseParser:
    """Subclass, set `key`, `bank`, `statement_type`, `extensions`, implement detect() and parse()."""

    key: str = ""
    bank: str = ""
    statement_type: str = ""
    extensions: tuple[str, ...] = ()

    def detect(self, source) -> bool:
        """source: first-page text (pdf) or openpyxl workbook (xlsx)."""
        raise NotImplementedError

    def parse(self, path: str) -> ParsedStatement:
        raise NotImplementedError
