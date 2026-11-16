"""
Bank statement parsing: one layout-driven engine for every bank (engine.py).

PDF words with positions -> rows starting with a date -> numeric columns found from aligned amounts, named by the
table header (layout.py); amounts in Turkish or US format (tokens.py); bank and statement type recognized from the
text (profiles.py). Each result carries a self-check against the statement's own totals (check_status/message).
`detect_and_parse(path)` returns a normalized `ParsedStatement`.
"""

from .base import ParsedLine, ParsedStatement, StatementParseError  # noqa: F401
from .registry import detect_and_parse  # noqa: F401
