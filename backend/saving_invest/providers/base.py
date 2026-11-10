import json
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

USER_AGENT = "app-manager/1.0 (+price fetcher)"


@dataclass(frozen=True)
class PriceQuote:
    source_code: str  # provider symbol, matched to Asset.source_code
    date: date
    buy: Decimal
    sell: Decimal
    source_time: datetime | None = None


class PriceProvider:
    """Adapter for one external price source. Subclasses implement `fetch()` (all symbols in one request)."""

    key = ""
    url = ""
    timeout = 20

    def fetch(self) -> list[PriceQuote]:
        raise NotImplementedError

    def get(self) -> bytes:
        request = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def get_json(self):
        return json.loads(self.get())


def tr_decimal(text: str) -> Decimal:
    """Turkish number format: '6.638' -> 6638, '79,53' -> 79.53, '3.302.578' -> 3302578."""
    return Decimal(str(text).strip().replace(".", "").replace(",", "."))
