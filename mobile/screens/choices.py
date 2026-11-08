"""Choice lists mirrored from the backend models (key, label)."""

NONE = "__none__"  # Dropdown sentinel for "no selection"

KINDS = [("expense", "Gider"), ("income", "Gelir")]

FREQUENCIES = [("weekly", "Haftalık"), ("monthly", "Aylık"), ("yearly", "Yıllık")]

ACCOUNT_TYPES = [("bank", "Banka Hesabı"), ("credit_card", "Kredi Kartı"), ("cash", "Nakit")]

BANKS = [
    ("ziraat", "Ziraat Bankası"), ("isbank", "İş Bankası"), ("garanti", "Garanti BBVA"),
    ("yapikredi", "Yapı Kredi"), ("akbank", "Akbank"), ("halkbank", "Halkbank"),
    ("vakifbank", "VakıfBank"), ("qnb", "QNB"), ("enpara", "Enpara"), ("denizbank", "DenizBank"),
    ("teb", "TEB"), ("ing", "ING"), ("kuveytturk", "Kuveyt Türk"), ("other", "Diğer"),
]

GOAL_STATUSES = [("active", "Aktif"), ("completed", "Tamamlandı"), ("cancelled", "İptal")]


def label(choices, key) -> str:
    return dict(choices).get(key, key or "")
