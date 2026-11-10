from datetime import datetime
from decimal import Decimal
from xml.etree import ElementTree

from django.conf import settings

from .base import PriceProvider, PriceQuote


class TcmbProvider(PriceProvider):
    """Central Bank of Turkey daily indicative rates (published on business days ~15:30, TRY per `Unit`)."""

    key = "tcmb"

    def __init__(self):
        self.url = settings.TCMB_RATES_URL

    def fetch(self):
        root = ElementTree.fromstring(self.get())
        day = datetime.strptime(root.attrib["Tarih"], "%d.%m.%Y").date()
        quotes = []
        for currency in root.iter("Currency"):
            buy, sell = currency.findtext("ForexBuying"), currency.findtext("ForexSelling")
            if not buy or not sell:
                continue
            unit = Decimal(currency.findtext("Unit") or "1")
            quotes.append(PriceQuote(currency.attrib["CurrencyCode"], day, Decimal(buy) / unit, Decimal(sell) / unit))
        return quotes
