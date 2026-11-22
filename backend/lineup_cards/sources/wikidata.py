"""
Wikidata adapter: runs a card source's SPARQL query and turns the result into import rows (the same columns as the
Excel template), so Wikidata cards go through the one import pipeline (validate → preview → staging → review).

Query contract (variables; unknown ones are ignored):
  ?item                       required, the Wikidata item (external key "wikidata:Q…")
  ?title_tr / ?title_mul / ?title_en
                              label: Turkish, else Wikidata's language-independent "mul" label (valid for every
                              language, so for Turkish too; flagged for a spelling check), else English (title_lang
                              "en": cannot be approved)
  ?subtitle                   optional
  ?sitelinks                  number of Wikipedia articles (popularity)
  ?trwiki                     Turkish Wikipedia article URL (page views → popularity)
  ?<attribute key>            value of that attribute of the card type (number or date)
  ?<key>_precision            dates: Wikidata time precision (9 year, 10 month, 11 day)
  ?<key>_date                 point in time of the value (e.g. population census): the latest wins
  ?<key>_rank                 statement rank: preferred wins, deprecated is dropped
  ?<extra field key>          display text (several values are joined)
Several rows per item are normal (one per value combination); they are merged here. Values are taken as the
source gives them: nothing is estimated or filled in.
"""

import time
from collections import Counter
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests
from django.conf import settings

from ..models import Attribute, CardSource
from .popularity import popularity

ENDPOINT = "https://query.wikidata.org/sparql"
PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/tr.wikipedia.org/all-access/user/"
             "{title}/monthly/{start}/{end}")
PREFERRED = "http://wikiba.se/ontology#PreferredRank"
DEPRECATED = "http://wikiba.se/ontology#DeprecatedRank"
PRECISION = {9: "year", 10: "month", 11: "day"}
RETRIES = 3  # on HTTP 429 (Wikidata rate limit), honouring Retry-After
MAX_WAIT = 60


class SourceError(Exception):
    pass


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = settings.WIKIMEDIA_USER_AGENT
    return s


def run_query(query: str, session: requests.Session | None = None) -> list[dict[str, str]]:
    """SPARQL result rows as {variable: value}."""
    session = session or _session()
    for attempt in range(RETRIES + 1):
        try:
            r = session.post(ENDPOINT, data={"query": query}, headers={"Accept": "application/sparql-results+json"},
                             timeout=180)
            if r.status_code == 429 and attempt < RETRIES:  # rate limited: wait as asked, then try again
                time.sleep(min(MAX_WAIT, int(r.headers.get("Retry-After", "10") or 10)))
                continue
            r.raise_for_status()
            bindings = r.json()["results"]["bindings"]
        except (requests.RequestException, ValueError, KeyError) as e:
            raise SourceError(f"Wikidata sorgusu çalışmadı: {e}") from e
        return [{k: v["value"] for k, v in b.items()} for b in bindings]
    raise SourceError("Wikidata sorgusu çalışmadı: hız sınırı")


# ---------------------------------------------------------------- values
def wikidata_date(value: str, precision: int | None) -> tuple[str | None, str | None]:
    """
    ("1453-05-29", None) / (None, error). Wikidata writes BC years in astronomical numbering (0 = 1 BC, -489 = 490 BC);
    our model uses negative years for BC without a year zero, so non-positive years shift by one.
    """
    text = value.removesuffix("Z").split("T")[0]
    negative = text.startswith("-")
    parts = text.lstrip("+-").split("-")
    try:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return None, f"tarih okunamadı ({value})"
    year = -year if negative else year
    if year <= 0:
        year -= 1
    if precision is not None and precision < 9:
        return None, "tarih yıldan kaba (on yıl / yüzyıl): kullanılamaz"
    kind = PRECISION.get(precision or 9, "day" if (precision or 0) > 11 else "year")
    if kind == "year":
        return str(year), None
    if kind == "month":
        return f"{year}-{month:02d}", None
    return f"{year}-{month:02d}-{day:02d}", None


def _number(value: str, places: int) -> str | None:
    try:
        n = Decimal(value)
    except InvalidOperation:
        return None
    return str(n.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def _disagree(attribute: Attribute, distinct: list[str]) -> bool:
    """Worth a reviewer's look: numbers more than 1 % apart, dates in different years."""
    if len(distinct) < 2:
        return False
    if attribute.value_type == Attribute.ValueType.DATE:
        return len({t.lstrip("-").split("-")[0] + ("-" if t.startswith("-") else "") for t in distinct}) > 1
    numbers = [abs(Decimal(t)) for t in distinct]
    low, high = min(numbers), max(numbers)
    return high > 0 and (high - low) / high > Decimal("0.01")


def _pick(attribute: Attribute, rows: list[dict], key: str) -> tuple[str | None, list[str]]:
    """The one value of an attribute among an item's rows: preferred rank, then the latest point in time; dates
    then the earliest (e.g. the first release). Disagreeing leftovers are reported, never averaged."""
    warnings = []
    candidates = []
    for r in rows:
        if key not in r or r.get(f"{key}_rank") == DEPRECATED:
            continue
        candidates.append(r)
    if not candidates:
        return None, warnings
    if any(r.get(f"{key}_rank") == PREFERRED for r in candidates):
        candidates = [r for r in candidates if r.get(f"{key}_rank") == PREFERRED]
    dated = [r for r in candidates if r.get(f"{key}_date")]
    if dated:
        latest = max(r[f"{key}_date"] for r in dated)
        candidates = [r for r in dated if r[f"{key}_date"] == latest]

    values = []
    for r in candidates:
        if attribute.value_type == Attribute.ValueType.DATE:
            precision = r.get(f"{key}_precision")
            text, error = wikidata_date(r[key], int(precision) if precision else None)
            if error:
                warnings.append(f"{attribute.name}: {error}")
                continue
            if not precision:
                warnings.append(f"{attribute.name}: kesinlik bilinmiyor, yıl kullanıldı")
            values.append(text)
        else:
            text = _number(r[key], attribute.decimal_places)
            if text is None:
                warnings.append(f"{attribute.name}: sayı okunamadı ({r[key]})")
                continue
            values.append(text)
    if not values:
        return None, warnings
    distinct = list(dict.fromkeys(values))
    if attribute.value_type == Attribute.ValueType.DATE:
        def order(t):
            negative = t.startswith("-")
            parts = [int(p) for p in t.lstrip("-").split("-")]
            return (-parts[0] if negative else parts[0], *(parts[1:] + [0, 0])[:2])
        chosen = min(distinct, key=order)
    else:
        counts = Counter(values)  # most frequent, ties broken by the smaller value: the same pick on every run
        chosen = min(distinct, key=lambda v: (-counts[v], Decimal(v)))
    if _disagree(attribute, distinct):
        shown = ", ".join(distinct[:4]) + ("…" if len(distinct) > 4 else "")
        warnings.append(f"{attribute.name}: kaynakta farklı değerler ({shown}); seçilen {chosen}")
    return chosen, warnings


# ---------------------------------------------------------------- page views
def _months(today: date, count: int = 3) -> tuple[str, str]:
    """First days of the last `count` full months, as the pageviews API wants them (YYYYMMDD00)."""
    year, month = today.year, today.month
    starts = []
    for _ in range(count):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        starts.append(date(year, month, 1))
    return starts[-1].strftime("%Y%m%d00"), starts[0].strftime("%Y%m%d00")


def monthly_views(article_url: str, session: requests.Session, today: date | None = None) -> float | None:
    """Average monthly user views of a Turkish Wikipedia article over the last 3 full months (None if unknown)."""
    title = urlsplit(article_url).path.removeprefix("/wiki/")
    if not title:
        return None
    start, end = _months(today or date.today())
    try:
        r = session.get(PAGEVIEWS.format(title=title.replace("/", "%2F"), start=start, end=end), timeout=20)
        if r.status_code == 404:
            return 0.0
        r.raise_for_status()
        items = r.json().get("items", [])
    except (requests.RequestException, ValueError):
        return None
    return sum(i["views"] for i in items) / 3 if items else 0.0


# ---------------------------------------------------------------- rows
def fetch_rows(source: CardSource) -> list[dict]:
    """Import rows (template columns + "_warnings") for the source's card type, most linked items first."""
    card_type = source.card_type
    attributes = {e.attribute.key: e.attribute for e in card_type.schema_attributes.select_related("attribute")}
    field_keys = [f.key for f in card_type.fields.all()]
    session = _session()
    by_item: dict[str, list[dict]] = {}
    for row in run_query(source.query, session):
        item = row.get("item", "")
        if item.startswith("http://www.wikidata.org/entity/Q"):
            by_item.setdefault(item, []).append(row)
    if not by_item:
        raise SourceError("Sorgu hiç ?item döndürmedi.")

    def sitelinks(rows):
        return max((int(r["sitelinks"]) for r in rows if r.get("sitelinks", "").isdigit()), default=0)

    ordered = sorted(by_item.items(), key=lambda kv: -sitelinks(kv[1]))[:source.limit]
    tags = ", ".join(t.strip() for t in source.tags.split(",") if t.strip())
    result = []
    for item, rows in ordered:
        qid = item.rsplit("/", 1)[1]
        first = rows[0]
        title_tr = next((r["title_tr"] for r in rows if r.get("title_tr")), "")
        title_mul = next((r["title_mul"] for r in rows if r.get("title_mul")), "")
        title_en = next((r["title_en"] for r in rows if r.get("title_en")), "")
        warnings = []
        if not title_tr and title_mul:
            title_tr = title_mul
            warnings.append("Çok dilli etiket (mul) kullanıldı: Türkçe yazımını kontrol edin")
        links = sitelinks(rows)
        views = None
        trwiki = next((r["trwiki"] for r in rows if r.get("trwiki")), "")
        if source.use_pageviews and trwiki:
            views = monthly_views(trwiki, session)
            time.sleep(0.05)  # be gentle with the Wikimedia API
        elif source.use_pageviews:
            warnings.append("Türkçe Vikipedi maddesi yok: tanınırlık yalnızca dil sayısından")
        out = {
            "external_key": f"wikidata:{qid}",
            "title": title_tr or title_en,
            "title_lang": "tr" if title_tr else "en",
            "subtitle": first.get("subtitle", ""),
            "popularity": popularity(links, views),
            "tags": tags,
            "source_url": f"https://www.wikidata.org/wiki/{qid}",
        }
        for key, attribute in attributes.items():
            value, notes = _pick(attribute, rows, key)
            warnings.extend(notes)
            if value is not None:
                out[key] = value
                if attribute.value_type == Attribute.ValueType.DATE and value.startswith("-"):
                    warnings.append(f"{attribute.name}: MÖ tarih, kaynakla karşılaştırın")
        for key in field_keys:
            texts = list(dict.fromkeys(r[key] for r in rows if r.get(key)))
            if texts:
                out[key] = ", ".join(texts[:3])
        out["_warnings"] = list(dict.fromkeys(warnings))
        result.append(out)
    return result
