from datetime import datetime

from django.conf import settings
from django.utils import timezone

from .base import PriceProvider, PriceQuote, tr_decimal


class AltinkaynakProvider(PriceProvider):
    """Altınkaynak gold/silver prices (TRY): [{"Kod", "Alis", "Satis", "GuncellenmeZamani"}, ...]."""

    key = "altinkaynak"

    def __init__(self):
        self.url = settings.ALTINKAYNAK_GOLD_URL

    def fetch(self):
        quotes = []
        for row in self.get_json():
            try:
                updated = timezone.make_aware(datetime.strptime(row["GuncellenmeZamani"], "%d.%m.%Y %H:%M:%S"))
                quotes.append(PriceQuote(row["Kod"], updated.date(), tr_decimal(row["Alis"]),
                                         tr_decimal(row["Satis"]), updated))
            except (KeyError, ValueError, ArithmeticError):
                continue  # skip malformed rows, keep the rest
        return quotes
