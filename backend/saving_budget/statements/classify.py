"""
Bank-independent rules applied to parsed lines:
  - skip suggestions (card payment, own-account transfer, investment/deposit movements)
  - category suggestion by keyword -> default category names (see services.DEFAULT_CATEGORIES)

Keywords are matched on accent-folded lowercase text ("MIGROS" == "mıgros" == "migros"),
starting at a word boundary. A trailing "$" also requires a word end ("taksi$" does not match "taksit").
"""

import re

from .base import ParsedLine
from .utils import fold, normalize

CARD_PAYMENT = ("kredi karti borc", "kart borc odeme", "kart borcu odeme")
INVESTMENT = (
    "yatirim fonu", "fon alis", "fon satis", "vadeli mevduat", "mevduat hesap", "yatirim menkul",
    "hisse senedi", "doviz alis", "doviz satis", "altin alis", "altin satis",
)
OUTGOING_TARGET = re.compile(r"hesabından (.+?) hesabına giden")
INCOMING_SOURCE = re.compile(r"a\.ş\. (.+?) hesabından")

# (keywords, kind, category name). First match wins; keep specific keywords before generic ones.
CATEGORY_RULES = [
    (("maas", "maasodemesi"), "income", "Maaş"),
    (("faiz", "getiri", "temettu"), "income", "Faiz/Getiri"),
    (("uber eats", "yemeksepeti", "trendyol yemek", "getir yemek", "catering", "cafe", "kafe", "restoran",
      "restaurant", "starbucks", "burger", "pizza", "doner$", "kahve"), "expense", "Yeme-İçme"),
    (("migros", "a101", "bim$", "sok$", "carrefour", "macrocenter", "metro market", "getir$", "saver gida",
      "file market", "market"), "expense", "Market"),
    (("turkcell", "vodafone", "turk telekom", "enerjisa", "igdas", "aski$", "dogalgaz", "elektrik",
      "su idaresi", "superonline", "turknet"), "expense", "Faturalar"),
    (("youtube", "spotify", "netflix", "tradingview", "disney", "exxen", "blutv", "apple.com", "icloud",
      "google one", "amazon prime", "steam", "playstation", "xbox"), "expense", "Abonelikler"),
    (("eczane", "eczaci", "hastane", "klinik", "saglik", "dis hekim"), "expense", "Sağlık"),
    (("kira bedeli", "kira$", "aidat"), "expense", "Kira"),
    (("opet", "shell", "petrol ofisi", "bp$", "total$", "akaryakit", "otopark", "taksi$", "bitaksi", "marti$",
      "ankarakart", "istanbulkart", "uber$"), "expense", "Ulaşım"),
    (("bubilet", "biletix", "passo", "sinema", "cinemaximum", "konser"), "expense", "Eğlence"),
    (("lc waikiki", "lcw", "defacto", "koton", "zara$", "mavi$", "boyner", "h&m"), "expense", "Giyim"),
    (("okul", "kurs$", "udemy", "kitap", "egitim"), "expense", "Eğitim"),
    (("ek hesap faiz", "kredi taksit", "nakit avans", "sigorta"), "expense", "Kredi/Borç"),
]


def _pattern(keyword: str) -> re.Pattern:
    word_end = keyword.endswith("$")
    body = re.escape(keyword.rstrip("$"))
    return re.compile(rf"(?<![a-z0-9]){body}" + (r"(?![a-z0-9])" if word_end else ""))


COMPILED_RULES = [(tuple(_pattern(k) for k in keywords), kind, name) for keywords, kind, name in CATEGORY_RULES]


def _compact(text: str) -> str:
    return normalize(text).replace(" ", "")


def skip_reason(line: ParsedLine, holder_name: str) -> str:
    folded = fold(line.raw_text or line.description)
    if any(k in folded for k in CARD_PAYMENT):
        return "card_payment"
    if any(k in folded for k in INVESTMENT):
        return "investment"
    holder = _compact(holder_name)
    if holder:
        text = normalize(line.raw_text or line.description)
        target = OUTGOING_TARGET.search(text) if line.amount < 0 else INCOMING_SOURCE.search(text)
        if target and _compact(target.group(1)).endswith(holder):
            return "transfer"
    return ""


def suggest_category_name(line: ParsedLine) -> str | None:
    text = fold(f"{line.description} {line.raw_text}")
    kind = "expense" if line.amount < 0 else "income"
    for patterns, rule_kind, name in COMPILED_RULES:
        if rule_kind == kind and any(p.search(text) for p in patterns):
            return name
    return None
