"""
Bank statement parsing.

Each parser handles one bank + statement type + file format, registers itself via
`@register`, and returns a normalized `ParsedStatement`. `detect_and_parse(path)` picks the
parser whose `detect()` accepts the file.
"""

from .base import ParsedLine, ParsedStatement, StatementParseError  # noqa: F401
from .registry import detect_and_parse  # noqa: F401
