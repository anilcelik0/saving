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
    hint: str = ""  # parser hint for classification, e.g. "card_payment"


@dataclass
class ParsedStatement:
    bank: str  # bank slug, e.g. "vakifbank" ("other" if not recognized)
    statement_type: str  # "account" | "card"
    lines: list[ParsedLine] = field(default_factory=list)
    period_start: date | None = None
    period_end: date | None = None
    closing_balance: Decimal | None = None
    holder_name: str = ""
    parser_key: str = ""  # set by the registry
    generic: bool = False  # bank or table header not recognized -> user should double-check lines
    # self-check against the statement's own totals: "ok" | "mismatch" | "unknown" + user-facing message
    check_status: str = ""
    check_message: str = ""
