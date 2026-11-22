"""
Ready-made Wikidata queries for the card types used so far (matched by card type key). Checked against the live
query service on 2026-11-22: 81 provinces, ~70 well-known films (80+ Wikipedias), ~150 battles (40+ Wikipedias).
An admin can copy and change them (e.g. lower the sitelinks threshold for more cards).
"""

LABELS = """
  OPTIONAL { ?item rdfs:label ?title_tr FILTER(LANG(?title_tr) = "tr") }
  OPTIONAL { ?item rdfs:label ?title_en FILTER(LANG(?title_en) = "en") }
  OPTIONAL { ?item rdfs:label ?title_mul FILTER(LANG(?title_mul) = "mul") }
  OPTIONAL { ?trwiki schema:about ?item ; schema:isPartOf <https://tr.wikipedia.org/> . }"""

PRESETS = {
    "province": {
        "name": "Wikidata: Türkiye illeri",
        "tags": "Coğrafya, Türkiye",
        "query": """SELECT ?item ?title_tr ?title_en ?title_mul ?sitelinks ?trwiki
       ?population ?population_date ?population_rank ?area ?area_rank ?region WHERE {
  ?item wdt:P31 wd:Q48336 ; wikibase:sitelinks ?sitelinks .   # province of Turkey
  OPTIONAL { ?item p:P1082 ?ps . ?ps ps:P1082 ?population ; wikibase:rank ?population_rank .
             OPTIONAL { ?ps pq:P585 ?population_date } }      # population (census date)
  OPTIONAL { ?item p:P2046 ?as . ?as wikibase:rank ?area_rank ;
             psv:P2046 [ wikibase:quantityAmount ?area ; wikibase:quantityUnit wd:Q712226 ] . }   # area in km²
  OPTIONAL { ?item wdt:P361 ?r . ?r wdt:P31 wd:Q1328578 ; rdfs:label ?region FILTER(LANG(?region) = "tr") }
""" + LABELS + "\n}",
    },
    "film": {
        "name": "Wikidata: tanınmış filmler",
        "tags": "Sinema",
        "query": """SELECT ?item ?title_tr ?title_en ?title_mul ?sitelinks ?trwiki ?date ?date_precision ?director WHERE {
  ?item wdt:P31 wd:Q11424 ; wikibase:sitelinks ?sitelinks .   # film
  FILTER(?sitelinks >= 80)
  OPTIONAL { ?item p:P577/psv:P577 [ wikibase:timeValue ?date ; wikibase:timePrecision ?date_precision ] . }
  OPTIONAL { ?item wdt:P57/rdfs:label ?director FILTER(LANG(?director) = "tr") }
""" + LABELS + "\n}",
    },
    "event": {
        "name": "Wikidata: tanınmış muharebeler",
        "tags": "Tarih, Savaş",
        "query": """SELECT ?item ?title_tr ?title_en ?title_mul ?sitelinks ?trwiki ?date ?date_precision WHERE {
  ?item wdt:P31 wd:Q178561 ; wikibase:sitelinks ?sitelinks .   # battle
  FILTER(?sitelinks >= 40)
  OPTIONAL {
    { ?item p:P585/psv:P585 [ wikibase:timeValue ?date ; wikibase:timePrecision ?date_precision ] . }  # point in time
    UNION
    { ?item p:P580/psv:P580 [ wikibase:timeValue ?date ; wikibase:timePrecision ?date_precision ] . }  # start time
  }
""" + LABELS + "\n}",
    },
}
