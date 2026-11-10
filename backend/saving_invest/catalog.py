"""Assets offered to users. `sync_assets()` upserts these rows; add an entry here to support a new asset."""

ASSETS = [
    # code, name, type, unit, quantity decimals, provider, provider symbol
    ("USD", "Amerikan Doları", "currency", "USD", 2, "tcmb", "USD"),
    ("EUR", "Euro", "currency", "EUR", 2, "tcmb", "EUR"),
    ("GOLD_GRAM", "Gram Altın", "gold", "gram", 3, "altinkaynak", "GA"),
    ("GOLD_QUARTER", "Çeyrek Altın", "gold", "adet", 0, "altinkaynak", "C"),
    ("GOLD_HALF", "Yarım Altın", "gold", "adet", 0, "altinkaynak", "Y"),
    ("GOLD_FULL", "Tam Altın", "gold", "adet", 0, "altinkaynak", "T"),
    ("SILVER_GRAM", "Gram Gümüş", "silver", "gram", 3, "altinkaynak", "AG_T"),
]
