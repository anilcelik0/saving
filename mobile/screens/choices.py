"""Choice lists mirrored from the backend models (key, label)."""

NONE = "__none__"  # Dropdown sentinel for "no selection"

KINDS = [("expense", "Gider"), ("income", "Gelir")]

REPEATS = [("none", "Tek seferlik"), ("recurring", "Düzenli (abonelik, kira, maaş...)"), ("installment", "Taksitli")]

FREQUENCIES = [("weekly", "Haftalık"), ("monthly", "Aylık"), ("yearly", "Yıllık")]

ACCOUNT_TYPES = [("bank", "Banka"), ("cash", "Nakit")]

TRADE_SIDES = [("buy", "Alış"), ("reduce", "Azaltma")]

DEPOSIT_STATUSES = [("active", "Aktif"), ("renewed", "Yenilendi"), ("closed", "Kapandı")]

MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
          "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def label(choices, key) -> str:
    return dict(choices).get(key, key or "")
