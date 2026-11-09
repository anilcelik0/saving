"""
Bank-independent rules applied to parsed lines:
  - skip suggestions (card payment, own-account transfer, investment/deposit movements)
  - category suggestion -> default category names (see services.DEFAULT_CATEGORIES); never empty

Category reasoning, in order (first match wins):
  1. Known merchants / bill payees  ("MIGROS" -> Market, "UBER EATS" -> Yeme-İçme, "TURKCELL" -> Faturalar)
  2. Purpose words in the text       ("kira bedeli" -> Kira, "aidat" -> Kira, "maaş" -> Maaş)
  3. Channel / transaction type      (ATM -> Nakit Çekim, FAST/EFT/Havale -> Para Transferi / Gelen Transfer,
                                      masraf/ücret/komisyon -> Banka Masrafı)
  4. Online purchase signals         (".com", iyzico/paytr/hepsipay gateways -> Online Alışveriş)
  5. Card refund                     (income on a card statement -> İade)
  6. Fallback                        (Diğer Gider / Diğer Gelir)

Keywords are matched on accent-folded lowercase text ("MİGROS" == "Mıgros" == "migros"),
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

EXPENSE, INCOME = "expense", "income"

# (keywords, kind, category name)
CATEGORY_RULES = [
    # --- income ---
    (("maas", "maasodemesi", "maas odemesi", "ucret odemesi", "bordro"), INCOME, "Maaş"),
    (("faiz", "getiri", "temettu", "kar payi"), INCOME, "Faiz/Getiri"),
    (("iade", "iptal", "refund"), INCOME, "İade"),
    (("fast", "eft", "havale", "gelen"), INCOME, "Gelen Transfer"),

    # --- 1-2. merchants & purposes (specific before generic) ---
    (("kira bedeli", "kira$", "aidat", "site yonetim"), EXPENSE, "Kira"),
    (("ek hesap faiz", "kredi taksit", "kredi odeme", "nakit avans", "kmh faiz", "gecikme faizi"), EXPENSE, "Kredi/Borç"),
    (("islem ucreti", "masraf", "komisyon", "kart aidati", "yillik kart", "hesap isletim", "bsmv", "kkdf",
      "sigorta"), EXPENSE, "Banka Masrafı"),
    (("uber eats", "yemeksepeti", "trendyol yemek", "getir yemek", "migros yemek", "catering", "cafe", "kafe",
      "restoran", "restaurant", "lokanta", "starbucks", "kahve", "burger", "mcdonald", "kfc", "popeyes",
      "dominos", "pizza", "doner", "donerci", "kebap", "kofte", "cigkofte", "tavuk", "pide", "lahmacun",
      "unlu mam", "firin", "pastane", "borek", "corek", "simit", "baklava", "tatli"), EXPENSE, "Yeme-İçme"),
    (("migros", "a101", "bim$", "bim a.s", "sok$", "sok market", "carrefour", "macrocenter", "metro market",
      "getir$", "getir perakende", "saver gida", "file market", "altunbilekler", "hakmar", "onur market",
      "happy center", "tarim kredi", "bizim toptan", "gimsa", "kim market", "market", "gida", "kasap",
      "manav", "sarkuteri"), EXPENSE, "Market"),
    (("turkcell", "vodafone", "turk telekom", "avea", "ttnet", "superonline", "turknet", "enerjisa", "ck enerji",
      "aydem", "gediz", "uedas", "toroslar", "igdas", "baskentgaz", "baskent gaz", "aksagaz", "aski$", "iski$",
      "dogalgaz", "elektrik", "su idaresi", "fatura"), EXPENSE, "Faturalar"),
    (("youtube", "spotify", "netflix", "tradingview", "disney", "exxen", "blutv", "gain$", "tod$", "apple.com",
      "icloud", "google", "amazon prime", "amazonprime", "steam", "playstation", "xbox", "chatgpt", "openai",
      "microsoft", "adobe", "canva"), EXPENSE, "Abonelikler"),
    (("eczane", "eczaci", "hastane", "klinik", "saglik", "dis hekim", "laboratuvar", "optik", "medikal"),
      EXPENSE, "Sağlık"),
    (("opet", "shell", "petrol ofisi", "bp$", "total$", "aytemiz", "akaryakit", "otopark", "taksi$", "bitaksi",
      "marti$", "ankarakart", "istanbulkart", "uber$", "obilet", "pamukkale", "metro turizm", "kamil koc",
      "thy$", "turk hava", "pegasus", "ajet", "sunexpress", "tcdd", "hgs$", "ogs$", "otoyol", "kopru"),
      EXPENSE, "Ulaşım"),
    (("bubilet", "biletix", "passo", "sinema", "cinemaximum", "paribu cineverse", "konser", "tiyatro", "muze"),
      EXPENSE, "Eğlence"),
    (("lc waikiki", "lcw", "defacto", "koton", "zara$", "mavi$", "boyner", "colins", "flo$", "deichmann",
      "ayakkabi", "giyim", "tekstil", "h&m", "pull&bear", "bershka", "network", "ipekyol"), EXPENSE, "Giyim"),
    (("okul", "kurs$", "udemy", "kitap", "kirtasiye", "egitim", "universite"), EXPENSE, "Eğitim"),
    (("arcelik", "beko", "vestel", "teknosa", "mediamarkt", "vatan bilgisayar", "ikea", "koctas", "bauhaus",
      "english home", "madame coco", "karaca", "elektronik", "mobilya", "powertec"), EXPENSE, "Ev & Elektronik"),
    (("gratis", "watsons", "rossmann", "eve$", "kuafor", "berber", "guzellik", "kozmetik", "sephora"),
      EXPENSE, "Kişisel Bakım"),

    # --- 3. channel / transaction type ---
    (("atm", "para cek", "nakit cekim"), EXPENSE, "Nakit Çekim"),
    (("fast", "eft", "havale", "para transferi", "giden"), EXPENSE, "Para Transferi"),

    # --- 4. online purchase signals ---
    (("trendyol", "hepsiburada", "hepsipay", "amazon", "n11", "ciceksepeti", "aliexpress", "temu", "shein",
      "iyzico", "paytr", "moneypay", "sipay", "param$", "shopier", "craftgate", "www.", ".com"),
      EXPENSE, "Online Alışveriş"),
]


def _pattern(keyword: str) -> re.Pattern:
    word_end = keyword.endswith("$")
    body = re.escape(keyword.rstrip("$"))
    start = "" if keyword.startswith(".") else r"(?<![a-z0-9])"  # ".com" may follow a letter
    return re.compile(start + body + (r"(?![a-z0-9])" if word_end else ""))


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


def suggest_category_name(line: ParsedLine, statement_type: str = "") -> str:
    """Always returns a category name (falls back to Diğer Gider / Diğer Gelir)."""
    kind = EXPENSE if line.amount < 0 else INCOME
    if kind == INCOME and statement_type == "card":
        return "İade"  # money in on a card statement (payments are dropped by parsers)
    text = fold(f"{line.description} {line.raw_text}")
    for patterns, rule_kind, name in COMPILED_RULES:
        if rule_kind == kind and any(p.search(text) for p in patterns):
            return name
    return "Diğer Gider" if kind == EXPENSE else "Diğer Gelir"
