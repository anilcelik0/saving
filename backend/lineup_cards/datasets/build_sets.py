"""
Builds the Line Up card sets as JSON files (the import format plus each card type's definition) from their sources.
A development tool, run by hand when a source publishes new figures; the app itself never connects to these sources
(cards enter the pool only through JSON files). Load the result with `manage.py load_lineup_sets`.

    docker compose exec web python lineup_cards/datasets/build_sets.py            # every set
    docker compose exec web python lineup_cards/datasets/build_sets.py films      # one set

Sources (every compared value is read from these, never typed in):
- provinces.json: population on 31.12.2025 from TÜİK's Address Based Population Registration System (Nüfus
  İstatistikleri Portalı, bulletin 53899 of 9 Feb 2026; the 81 provinces must add up to TÜİK's Türkiye total);
  area from Harita Genel Müdürlüğü "İl ve ilçe yüz ölçümleri" (2026 map, km²; TÜİK publishes density, not area).
- footballers.json: Süper Lig players with 100+ league goals, English Wikipedia "List of Süper Lig top scorers"
  (its table cites Mackolik), pinned to the revision that was read.
- films.json: rating and vote count from IMDb's dataset title.ratings.tsv.gz (IMDb's terms allow personal and
  non-commercial use only: settle licensing before release); release year (earliest publication date) and director
  from Wikidata; the Turkish title from Turkish Wikipedia.
Popularity (0-100, how well known a card is; easy decks pick well-known cards) is a game setting, not a source value:
each builder documents its formula.
"""

import gzip
import html
import io
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
USER_AGENT = "LineUpDataBuilder/1.0 (+https://appmanager.com.tr)"


def http(url: str, data: dict | None = None, timeout: int = 90) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def get_json(url: str, **params) -> dict:
    return json.loads(http(f"{url}?{urllib.parse.urlencode(params)}"))


def turkish_title(upper: str) -> str:
    """ŞANLIURFA -> Şanlıurfa, İZMİR -> İzmir (Turkish dotted / dotless i)."""
    lower = upper.replace("I", "ı").replace("İ", "i").lower()
    first = {"i": "İ", "ı": "I"}.get(lower[0], lower[0].upper())
    return first + lower[1:]


def clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, round(value)))


def write(name: str, definition: dict, cards: list[dict], meta: dict) -> None:
    data = {"card_type": definition["key"], "definition": definition,
            "meta": {"built_at": datetime.now(UTC).isoformat(timespec="seconds"), **meta}, "cards": cards}
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{name}: {len(cards)} cards")


# ---------------------------------------------------------------- provinces (TÜİK + HGM)
NIP = "https://nip.tuik.gov.tr"
TUIK_YEAR = "2025"
TUIK_SOURCE = "https://data.tuik.gov.tr/Bulten/Index?p=Adrese-Dayali-Nufus-Kayit-Sistemi-Sonuclari-2025-53899"
HGM_SOURCE = "https://www.harita.gov.tr/il-ve-ilce-yuzolcumleri"
HGM_XLSX = "https://www.harita.gov.tr/uploads/files-folder/il_ilce_alanlari.xlsx"

PROVINCE = {
    "key": "province", "name": "İl", "emoji": "🏙️",
    "description": "Türkiye'nin 81 ili: nüfus (TÜİK ADNKS) ve yüzölçümü (Harita Genel Müdürlüğü).",
    "attributes": [
        {"key": "population", "name": "Nüfus", "value_type": "number", "unit": "kişi", "decimal_places": 0,
         "lower_label": "daha az nüfuslu", "higher_label": "daha kalabalık", "required": True},
        {"key": "area", "name": "Yüzölçümü", "value_type": "number", "unit": "km²", "decimal_places": 0,
         "lower_label": "daha küçük", "higher_label": "daha büyük", "required": True},
    ],
    "fields": [],
}


def _tuik_table(level: str) -> list[list[str]]:
    """Rows of the portal's "population by sex" table for a level (TÜRKİYE or a province), as the site loads it."""
    page = http(f"{NIP}/Home/GetInformation",
                {"status": "1", "name": "CinsiyeteGoreNufus", "value": level}).decode("utf-8")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if cells:
            rows.append(cells)
    return rows


def _tuik_population(level: str) -> int:
    for year, name, total, *_ in _tuik_table(level):
        if year == TUIK_YEAR and name == level:
            return int(total.replace(".", ""))
    raise SystemExit(f"TÜİK: {TUIK_YEAR} nüfusu bulunamadı: {level}")


def build_provinces() -> None:
    from openpyxl import load_workbook  # backend requirement (run inside the web container)

    # The 81 current provinces as HGM lists them (TÜİK's list also holds historical ones such as Bayazıt).
    sheet = load_workbook(io.BytesIO(http(HGM_XLSX)), data_only=True).worksheets[0]
    areas = {r[2].strip(): r[3] for r in sheet.iter_rows(min_row=6, values_only=True)
             if r[0] is None and isinstance(r[2], str) and isinstance(r[3], int | float)}
    if len(areas) != 81:
        raise SystemExit(f"HGM il listesi 81 değil: {len(areas)}")

    page = http(f"{NIP}/Home/CinsiyeteGoreNufus", {}).decode("utf-8")
    tuik_names = {html.unescape(v) for v in re.findall(r'<option value="([^"]*)"', page)}
    populations = {}
    for name in areas:
        tuik_name = name.replace("Â", "A")  # HGM HAKKÂRİ = TÜİK HAKKARİ
        if tuik_name not in tuik_names:
            raise SystemExit(f"TÜİK'te il bulunamadı: {name}")
        populations[name] = _tuik_population(tuik_name)
        time.sleep(0.3)  # gentle on the portal
    total = _tuik_population("TÜRKİYE")
    if sum(populations.values()) != total:
        raise SystemExit(f"İllerin toplamı ({sum(populations.values())}) TÜİK Türkiye toplamı ({total}) değil")

    cards = []
    for name in areas:
        population = populations[name]
        cards.append({
            "external_key": f"il:{name}",
            "title": turkish_title(name),
            "title_lang": "tr",
            # 50 at 100 000 people, +12 per tenfold (İstanbul ~76, Bayburt ~49): every province is known in Türkiye
            "popularity": clamp(50 + 12 * (math.log10(population) - 5), 30, 95),
            "tags": ["Türkiye", "İller"],
            "source_url": TUIK_SOURCE,
            "population": population,
            "area": round(areas[name]),
            "sources": {"area": HGM_SOURCE},
        })
    write("provinces.json", PROVINCE, cards, {
        "sources": {"population": f"TÜİK ADNKS, 31.12.{TUIK_YEAR} ({TUIK_SOURCE}; nip.tuik.gov.tr)",
                    "area": f"Harita Genel Müdürlüğü, il yüz ölçümleri 2026 ({HGM_SOURCE})"},
        "check": f"81 il toplamı = TÜİK Türkiye toplamı {total}",
    })


# ---------------------------------------------------------------- footballers (Süper Lig 100+ goals)
WIKI_EN = "https://en.wikipedia.org/w/api.php"
SCORERS_PAGE = "List_of_Süper_Lig_top_scorers"

FOOTBALLER = {
    "key": "footballer", "name": "Futbolcu", "emoji": "⚽",
    "description": "Süper Lig tarihinde 100 ve üzeri lig golü atan oyuncular.",
    "attributes": [
        {"key": "superlig_goals", "name": "Süper Lig golü", "value_type": "number", "unit": "gol",
         "decimal_places": 0, "lower_label": "daha az gol", "higher_label": "daha çok gol", "required": True},
    ],
    "fields": [{"key": "clubs", "label": "Kulüpler (gol)", "required": False}],
}

ATTRS = re.compile(r'^\s*(?:[a-z-]+="[^"]*"\s*)+\|(?!\|)')
LINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")
CLUB = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]\s*(?:\((\d+)/(\d+)\))?")
REFS = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S)


def _cells(row: str) -> list[str]:
    cells = []
    for line in REFS.sub("", row).strip().splitlines():
        if line.startswith("|") and not line.startswith(("|-", "|}", "|+")):
            cells.append(ATTRS.sub("", line[1:]).strip())
    return cells


def build_footballers() -> None:
    parsed = get_json(WIKI_EN, action="parse", page=SCORERS_PAGE, prop="wikitext|revid", section=1, format="json",
                      formatversion=2)["parse"]
    text, revid = parsed["wikitext"], parsed["revid"]
    updated = re.search(r"\{\{updated\|([^}]+)\}\}", text)
    table = text[text.index("{|"):text.index("\n|}")]
    source = f"https://en.wikipedia.org/w/index.php?title={urllib.parse.quote(SCORERS_PAGE)}&oldid={revid}"
    cards = []
    for row in table.split("\n|-")[1:]:
        cells = _cells(row)
        at = next((i for i, c in enumerate(cells) if "{{flagicon" in c), None)
        if at is None:
            continue
        link = LINK.search(cells[at])
        target = link[1].strip()
        name = re.sub(r"\s*\([^)]*\)$", "", (link[2] or target).strip("' "))
        goals = int(re.sub(r"\D", "", cells[at + 1]))
        first, last = cells[at + 4], cells[at + 5]
        # "[[Galatasaray S.K. (football)|Galatasaray]] (228/393)": club, then (goals/apps) unless it is the only club
        clubs = [((m[2] or m[1]).strip(), int(m[3]) if m[3] else goals) for m in CLUB.finditer(cells[at + 6])]
        clubs.sort(key=lambda c: -c[1])
        cards.append({
            "external_key": f"enwiki:{target}",
            "title": name,
            "subtitle": f"{first}–{last}",
            "title_lang": "tr",  # a person's name is the same in Turkish
            # 55 at 100 goals up to 90 at 250: all of them are league legends, the top ones household names
            "popularity": clamp(55 + 35 * (goals - 100) / 150, 40, 95),
            "tags": ["Futbol", "Süper Lig", *dict.fromkeys(c for c, _ in clubs)],
            "source_url": source,
            "superlig_goals": goals,
            "clubs": ", ".join(f"{c} ({g})" for c, g in clubs),
        })
    if len(cards) < 20:
        raise SystemExit(f"Gol listesi beklenenden kısa: {len(cards)} oyuncu")
    write("footballers.json", FOOTBALLER, cards, {
        "sources": {"superlig_goals": f"Wikipedia, List of Süper Lig top scorers (revizyon {revid}, "
                                      f"tablo güncelleme: {updated[1] if updated else '?'}; kaynak Mackolik)"},
        "note": "Kalın yazılan (hâlâ Süper Lig'de oynayan) oyuncuların gol sayısı değişir; seti yeniden üretin.",
    })


# ---------------------------------------------------------------- films (IMDb + Wikidata)
IMDB_RATINGS = "https://datasets.imdbws.com/title.ratings.tsv.gz"
WIKIDATA = "https://www.wikidata.org/w/api.php"

# 25 well-known world classics, by English Wikipedia article (identity only: every value is read from the sources)
FILMS = [
    "Citizen Kane", "Casablanca (film)", "Seven Samurai", "12 Angry Men (1957 film)", "Vertigo (film)",
    "Psycho (1960 film)", "The Good, the Bad and the Ugly", "2001: A Space Odyssey", "The Godfather",
    "One Flew Over the Cuckoo's Nest (film)", "Star Wars (film)", "The Shining (film)", "Back to the Future",
    "Goodfellas", "The Silence of the Lambs (film)", "Schindler's List", "The Shawshank Redemption", "Pulp Fiction",
    "Forrest Gump", "Life Is Beautiful", "Titanic (1997 film)", "The Matrix", "Spirited Away",
    "The Lord of the Rings: The Return of the King", "The Dark Knight",
]

FILM = {
    "key": "film", "name": "Film", "emoji": "🎬",
    "description": "Dünya sinemasının bilinen klasikleri: çıkış yılı ve IMDb puanı.",
    "attributes": [
        {"key": "date", "name": "Tarih", "value_type": "date", "unit": "", "decimal_places": 0,
         "lower_label": "daha eski", "higher_label": "daha yeni", "required": True},
        {"key": "imdb_rating", "name": "IMDb puanı", "value_type": "number", "unit": "", "decimal_places": 1,
         "lower_label": "daha düşük puanlı", "higher_label": "daha yüksek puanlı", "required": True},
    ],
    "fields": [{"key": "director", "label": "Yönetmen", "required": False}],
}


def _labels(entity: dict) -> str | None:
    """Turkish label, else Wikidata's multilingual default ("mul", used for many people), else English."""
    labels = entity.get("labels", {})
    return (labels.get("tr") or labels.get("mul") or labels.get("en") or {}).get("value")


def build_films() -> None:
    pages = get_json(WIKI_EN, action="query", titles="|".join(FILMS), redirects=1, prop="pageprops|langlinks",
                     ppprop="wikibase_item", lllang="tr", lllimit="max", format="json", formatversion=2)["query"]
    by_title = {p["title"]: p for p in pages["pages"]}
    resolved = {r["from"]: r["to"] for r in pages.get("redirects", []) + pages.get("normalized", [])}
    films = []
    for title in FILMS:
        page = by_title.get(resolved.get(title, title))
        if not page or "pageprops" not in page:
            raise SystemExit(f"Wikipedia'da bulunamadı: {title}")
        tr = (page.get("langlinks") or [{}])[0].get("title")
        films.append({"en": page["title"], "qid": page["pageprops"]["wikibase_item"], "trwiki": tr})

    entities = get_json(WIKIDATA, action="wbgetentities", ids="|".join(f["qid"] for f in films),
                        props="claims|labels", languages="tr|en", format="json")["entities"]
    director_ids = set()
    for f in films:
        claims = entities[f["qid"]]["claims"]
        f["imdb"] = next(c["mainsnak"]["datavalue"]["value"] for c in claims["P345"]
                         if c["mainsnak"]["datavalue"]["value"].startswith("tt"))
        years = [int(c["mainsnak"]["datavalue"]["value"]["time"][1:5]) for c in claims.get("P577", [])
                 if c["mainsnak"].get("datavalue")]
        if not years:
            raise SystemExit(f"Wikidata'da çıkış tarihi yok: {f['en']}")
        f["year"] = min(years)
        f["directors"] = [c["mainsnak"]["datavalue"]["value"]["id"] for c in claims.get("P57", [])
                          if c["mainsnak"].get("datavalue")]
        director_ids.update(f["directors"])
        f["trlabel"] = entities[f["qid"]].get("labels", {}).get("tr", {}).get("value")
    people = get_json(WIKIDATA, action="wbgetentities", ids="|".join(sorted(director_ids)), props="labels",
                      languages="tr|mul|en", format="json")["entities"]

    wanted = {f["imdb"] for f in films}
    ratings = {}
    with gzip.open(io.BytesIO(http(IMDB_RATINGS, timeout=300)), "rt", encoding="utf-8") as tsv:
        for line in tsv:
            tconst, rating, votes = line.rstrip("\n").split("\t")
            if tconst in wanted:
                ratings[tconst] = (rating, int(votes))
    missing = sorted(wanted - set(ratings))
    if missing:
        raise SystemExit(f"IMDb puanı bulunamadı: {missing}")

    cards = []
    for f in films:
        rating, votes = ratings[f["imdb"]]
        title = re.sub(r"\s*\([^)]*\)$", "", f["trwiki"]) if f["trwiki"] else f["trlabel"]
        cards.append({
            "external_key": f"imdb:{f['imdb']}",
            "title": title or f["en"],
            "subtitle": re.sub(r"\s*\([^)]*\)$", "", f["en"]),
            "title_lang": "tr" if title else "en",
            # 55 at ~316 000 IMDb votes, +25 per tenfold (most-voted classics ~80)
            "popularity": clamp(55 + 25 * (math.log10(votes) - 5.5), 40, 95),
            "tags": ["Sinema", "Dünya klasikleri"],
            "source_url": f"https://www.imdb.com/title/{f['imdb']}/",
            "date": str(f["year"]),
            "imdb_rating": rating,
            "director": ", ".join(filter(None, (_labels(people[d]) for d in f["directors"]))),
            "sources": {"date": f"https://www.wikidata.org/wiki/{f['qid']}"},
        })
    write("films.json", FILM, cards, {
        "sources": {"imdb_rating": f"IMDb dataset title.ratings.tsv.gz (indirildi {datetime.now(UTC):%Y-%m-%d})",
                    "date": "Wikidata P577, en erken yayın tarihinin yılı", "title": "Türkçe Vikipedi madde adı"},
        "imdb_votes": {f["imdb"]: ratings[f["imdb"]][1] for f in films},
        "license": "IMDb verisi yalnızca kişisel ve ticari olmayan kullanım içindir; yayından önce lisans gerekir.",
    })


BUILDERS = {"provinces": build_provinces, "footballers": build_footballers, "films": build_films}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for set_name in sys.argv[1:] or list(BUILDERS):
        BUILDERS[set_name]()
