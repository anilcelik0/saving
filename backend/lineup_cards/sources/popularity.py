"""
Popularity 0-100 from source signals, never typed in by hand for sourced cards:
- sitelinks: in how many Wikipedia languages the item has an article (worldwide recognition), log scale, 250+ = 100;
- trwiki page views: monthly average views of the Turkish article (recognition in Turkey), log scale, 100k+ = 100.
With both, the average; with sitelinks only, that score.
"""

import math

SITELINKS_FULL = 250
MONTHLY_VIEWS_FULL = 100_000


def sitelinks_score(sitelinks: int) -> float:
    return min(100.0, 100 * math.log1p(max(0, sitelinks)) / math.log1p(SITELINKS_FULL))


def pageviews_score(monthly_views: float) -> float:
    return min(100.0, 100 * math.log10(1 + max(0.0, monthly_views)) / math.log10(1 + MONTHLY_VIEWS_FULL))


def popularity(sitelinks: int, monthly_views: float | None) -> int:
    s = sitelinks_score(sitelinks)
    return round(s if monthly_views is None else (s + pageviews_score(monthly_views)) / 2)
