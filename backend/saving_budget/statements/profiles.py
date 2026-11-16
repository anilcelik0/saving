"""
Bank and statement-type recognition (names and hints only; there is no per-bank parsing code).
Searched in the statement's own text without the transaction rows, so a counterparty bank in a description
("... Ziraat Bankası hesabına giden") does not decide the bank.
"""

import re

# (folded phrase, bank slug); brands that print their parent bank's name come first
BANK_PHRASES = [
    ("enpara", "enpara"),
    ("vakifbank", "vakifbank"), ("vb musteri no", "vakifbank"), ("vb mus. no", "vakifbank"),
    ("garanti bbva", "garanti"), ("garantibbva", "garanti"),
    ("qnb", "qnb"), ("akbank", "akbank"), ("ziraat", "ziraat"), ("is bankasi", "isbank"), ("isbank", "isbank"),
    ("yapi kredi", "yapikredi"), ("halkbank", "halkbank"), ("denizbank", "denizbank"), ("kuveyt turk", "kuveytturk"),
    ("ing bank", "ing"), ("teb", "teb"), ("fibabanka", "fibabanka"), ("sekerbank", "sekerbank"),
    ("albaraka", "albaraka"), ("odeabank", "odeabank"), ("papara", "papara"), ("garanti", "garanti"),
]
PRIORITY = ("enpara",)  # sub-brands: their statements also mention the parent bank

CARD_HINTS = (
    "hesap kesim", "son odeme tarihi", "asgari odeme", "minimum odeme", "kart limiti", "ekstre borcu",
    "donem borcu", "kredi karti ekstresi", "kredi karti hesap ozeti",
)


def detect_bank(folded: str) -> str:
    counts = {}
    for phrase, slug in BANK_PHRASES:
        hits = re.findall(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", folded)
        if hits:
            if slug in PRIORITY:
                return slug
            counts[slug] = counts.get(slug, 0) + len(hits)
    return max(counts, key=counts.get) if counts else "other"


def is_card(folded: str) -> bool:
    return sum(hint in folded for hint in CARD_HINTS) >= 2
