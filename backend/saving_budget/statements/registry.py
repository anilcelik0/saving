from .base import ParsedStatement, StatementParseError
from .engine import parse_pdf_pages, parse_table, read_table
from .layout import extract_pages

NOT_READ = ("Bu ekstreden hareket okunamadı. Ekstreyi \"Sorun bildir\" ile bize gönderirseniz okuyucuyu bu "
            "formata göre geliştirebiliriz.")


def file_type(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "xlsx"):
        raise StatementParseError("Desteklenmeyen dosya türü. PDF veya Excel (.xlsx) yükleyin.")
    return ext


def read_input(path: str):
    """File -> the engine's input: PDF words per page or Excel cell values."""
    ext = file_type(path)
    try:
        return ext, (extract_pages(path) if ext == "pdf" else read_table(path))
    except Exception as exc:
        raise StatementParseError("Dosya okunamadı. Bozuk veya şifreli olabilir.") from exc


def parse_input(ext: str, data) -> ParsedStatement:
    """Engine input (from a file or a sample fixture) -> parsed statement."""
    try:
        result = parse_pdf_pages(data) if ext == "pdf" else parse_table(data)
    except StatementParseError:
        raise
    except Exception as exc:
        raise StatementParseError("Dosya okunamadı. Bozuk veya şifreli olabilir.") from exc
    if not result.lines:
        raise StatementParseError(NOT_READ)
    result.parser_key = f"engine_{ext}"
    return result


def detect_and_parse(path: str) -> ParsedStatement:
    """One engine for every bank (statements/engine.py); bank and statement type are recognized from the text."""
    return parse_input(*read_input(path))


BANK_LABELS = {
    "vakifbank": "VakıfBank", "qnb": "QNB", "garanti": "Garanti BBVA", "enpara": "Enpara", "akbank": "Akbank",
    "ziraat": "Ziraat Bankası", "isbank": "İş Bankası", "yapikredi": "Yapı Kredi", "halkbank": "Halkbank",
    "denizbank": "DenizBank", "kuveytturk": "Kuveyt Türk", "ing": "ING", "teb": "TEB", "fibabanka": "Fibabanka",
    "sekerbank": "Şekerbank", "albaraka": "Albaraka", "odeabank": "Odeabank", "papara": "Papara",
    "other": "Diğer banka",
}
