import openpyxl

from .base import BaseParser, ParsedStatement, StatementParseError
from .utils import first_page_text

PARSERS: list[BaseParser] = []


def register(cls):
    PARSERS.append(cls())
    return cls


def detect_and_parse(path: str) -> ParsedStatement:
    from . import parsers  # noqa: F401  (registers all parsers)

    ext = path.rsplit(".", 1)[-1].lower()
    try:
        if ext == "pdf":
            source = first_page_text(path)
        elif ext == "xlsx":
            source = openpyxl.load_workbook(path, data_only=True, read_only=True)
        else:
            raise StatementParseError("Desteklenmeyen dosya türü. PDF veya Excel (.xlsx) yükleyin.")
    except StatementParseError:
        raise
    except Exception as exc:
        raise StatementParseError("Dosya okunamadı. Bozuk veya şifreli olabilir.") from exc

    for parser in PARSERS:
        if ext in parser.extensions and parser.detect(source):
            result = parser.parse(path)
            result.parser_key, result.generic = parser.key, parser.generic
            if not result.lines:
                if parser.generic:
                    raise StatementParseError(
                        "Bu ekstreden hareket okunamadı. Bankanız için özel destek eklenmesi gerekebilir."
                    )
                raise StatementParseError("Ekstrede aktarılacak hareket bulunamadı.")
            return result
    raise StatementParseError("Bu ekstre formatı henüz desteklenmiyor.")


BANK_LABELS = {
    "vakifbank": "VakıfBank", "qnb": "QNB", "garanti": "Garanti BBVA", "enpara": "Enpara", "akbank": "Akbank",
    "ziraat": "Ziraat Bankası", "isbank": "İş Bankası", "yapikredi": "Yapı Kredi", "halkbank": "Halkbank",
    "denizbank": "DenizBank", "kuveytturk": "Kuveyt Türk", "ing": "ING", "teb": "TEB", "fibabanka": "Fibabanka",
    "sekerbank": "Şekerbank", "albaraka": "Albaraka", "odeabank": "Odeabank", "papara": "Papara",
    "other": "Diğer banka",
}
