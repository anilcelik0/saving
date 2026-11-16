from .base import ParsedStatement, StatementParseError
from .engine import parse_pdf, parse_xlsx

NOT_READ = ("Bu ekstreden hareket okunamadı. Ekstreyi \"Sorun bildir\" ile bize gönderirseniz okuyucuyu bu "
            "formata göre geliştirebiliriz.")


def detect_and_parse(path: str) -> ParsedStatement:
    """One engine for every bank (statements/engine.py); bank and statement type are recognized from the text."""
    ext = path.rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "xlsx"):
        raise StatementParseError("Desteklenmeyen dosya türü. PDF veya Excel (.xlsx) yükleyin.")
    try:
        result = parse_pdf(path) if ext == "pdf" else parse_xlsx(path)
    except StatementParseError:
        raise
    except Exception as exc:
        raise StatementParseError("Dosya okunamadı. Bozuk veya şifreli olabilir.") from exc
    if not result.lines:
        raise StatementParseError(NOT_READ)
    result.parser_key = f"engine_{ext}"
    return result


BANK_LABELS = {
    "vakifbank": "VakıfBank", "qnb": "QNB", "garanti": "Garanti BBVA", "enpara": "Enpara", "akbank": "Akbank",
    "ziraat": "Ziraat Bankası", "isbank": "İş Bankası", "yapikredi": "Yapı Kredi", "halkbank": "Halkbank",
    "denizbank": "DenizBank", "kuveytturk": "Kuveyt Türk", "ing": "ING", "teb": "TEB", "fibabanka": "Fibabanka",
    "sekerbank": "Şekerbank", "albaraka": "Albaraka", "odeabank": "Odeabank", "papara": "Papara",
    "other": "Diğer banka",
}
