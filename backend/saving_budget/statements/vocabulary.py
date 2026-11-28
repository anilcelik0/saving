"""
Every word list the statement engine reads labels with, in one place. A new bank usually needs only a phrase here:
compare on accent-folded lowercase text (utils.fold: "Dönem İçi" -> "donem ici"). Bank names: profiles.py,
category keywords: classify.py.
"""

import re

# ---------------------------------------------------------------- transaction table header -> column role
# compared on folded words without punctuation ("Tutar(TL)" -> "tutar", "Tutar/Taksit" -> "tutartaksit");
# the longest phrase wins
ROLE_PHRASES = [
    (("islem", "tarihi"), "date"), (("islem", "tarih"), "date"), (("hareket", "tarihi"), "date"),
    (("tarih",), "date"), (("tarihi",), "date"), (("valor",), "date"),
    (("saat",), "time"),
    (("islem", "no"), "ref"), (("dekont", "no"), "ref"), (("fis", "no"), "ref"), (("referans",), "ref"),
    (("ref", "no"), "ref"), (("sira", "no"), "ref"),
    (("islem", "aciklamasi"), "description"), (("donem", "ici", "islemler"), "description"),
    (("aciklama",), "description"), (("aciklamasi",), "description"), (("isyeri",), "description"),
    (("islemler",), "description"),
    (("islem", "tutari"), "amount"), (("tutar",), "amount"), (("tutari",), "amount"), (("miktar",), "amount"),
    (("kalan", "borc"), "installment"), (("kalan", "taksit"), "installment"), (("taksit",), "installment"),
    (("kalan", "tutartaksit"), "installment"), (("tutartaksit",), "installment"), (("kalan", "tutar"), "installment"),
    (("borc",), "debit"), (("cikan",), "debit"), (("alacak",), "credit"), (("giren",), "credit"),
    (("yatan",), "credit"),
    (("bakiye",), "balance"), (("bakiyesi",), "balance"),
    (("bonus",), "bonus"), (("puan",), "bonus"), (("worldpuan",), "bonus"), (("parapuan",), "bonus"),
    (("maxipuan",), "bonus"), (("chip", "para"), "bonus"), (("parafpara",), "bonus"),
    (("doviz",), "original"), (("orijinal",), "original"),
    (("islem",), "description"),
]
ROLE_PHRASES.sort(key=lambda p: -len(p[0]))

# ---------------------------------------------------------------- statement summary (card statements)
# label -> role of the amount printed after it ("Dönem Borcunuz : 15.166,39") or under it (summary grids:
# "Önceki Bakiye | Dönem Harcamaları | Faiz ve Ücretler | Ödemeleriniz | Dönem Borcunuz"). First match wins.
#   previous: last statement's debt   charges: spending (+ installments)   cash: cash advance
#   fees: interest / fees / taxes      credits: payments (+ refunds)        debt: this statement's debt
SUMMARY_ROLES = [
    ("previous", ("onceki", "devir", "devreden", "gecen donem")),
    ("debt", ("donem borcu", "donem borcunuz", "ekstre borcu", "ekstre borcunuz", "hesap ozeti borcu",
              "toplam borcunuz", "guncel donem borcu", "genel toplam", "odenecek tutar")),
    ("credits", ("odemeler", "odemeleriniz", "alacaklar", "yapilan odeme", "odeme ve alacak")),
    ("charges", ("harcama", "donem ici islemler", "islemler", "yansiyan taksit")),
    ("cash", ("nakit avans", "nakit cekim")),
    ("fees", ("faiz", "ucret", "vergi", "fon", "masraf", "komisyon")),
]
# labels that are never one of the totals above (limits, minimum payment, points, rates, fee schedules)
SUMMARY_IGNORE = ("limit", "asgari", "minimum", "min.", "min ", "oran", "puan", "bonus", "kalan", "kullanilabilir",
                  "%", "arasina", "uzerine", "ucreti", "ucretidir", "son odeme", "tutarli islem", "sigorta", " icin ",
                  " sgk ", "altindaki", "ustundeki")
SUMMARY_OPERATORS = {"+", "-", "=", "−"}

# ---------------------------------------------------------------- transaction rows
PAYMENT_WORDS = ("odeme", "tesekkur")  # card credits with these words are payments, the rest are refunds
SUMMARY_WORDS = ("onceki donem", "onceki ekstre", "bir onceki", "devir", "toplam")  # rows that are not transactions
FILLER_WORDS = {"bosluk", "bboosslluukk", "bboosluskluk"}  # layout filler printed in white

# "388.956,61 TL'lik işlemin 20 / 40 taksidi" (detail line under an installment row)
DETAIL_INSTALLMENT = re.compile(r"(\d{1,3})\s*/\s*(\d{1,3})\s*\.?\s*taksi[dt]")

# ---------------------------------------------------------------- dates, holder, balances
CUT_OFF = re.compile(r"(hesap\s+kesim\s+tarihi|ekstre\s+tarihi|kesim\s+tarihi|hesap\s+özeti\s+tarihi)", re.I)
PREVIOUS_CUT_OFF = re.compile(r"önceki\s+hesap\s+kesim\s+tarihiniz", re.I)
PERIOD = re.compile(r"tarih\s+aral[ıi]ğ[ıi]", re.I)
HOLDER = re.compile(r"^(?:hesap\s+sahibi|ad[ıi]?\s+soyad[ıi]?|müşteri\s+ad[ıi])\s*:?\s*(.+)$", re.I)
CLOSING = re.compile(r"(?<![a-zçğıöşü])bakiye\s*:\s*(\S+)", re.I)
