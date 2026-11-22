"""
Source adapters feeding the one import pipeline (importer.validate → CardImport preview → importer.apply to staging).
An adapter turns a CardSource into rows with the template's columns (+ "_warnings"); see wikidata.py.
"""

from django.utils import timezone

from .. import importer
from ..models import CardImport, CardSource
from . import wikidata
from .wikidata import SourceError

ADAPTERS = {CardSource.Kind.WIKIDATA: wikidata.fetch_rows}

__all__ = ["SourceError", "run_source"]


def run_source(source: CardSource, user=None, auto_apply: bool = False) -> CardImport:
    """
    Fetch → validate → a CardImport. Preview by default (applied from the admin after review); auto_apply (monthly
    refresh) applies new and changed rows right away: they land in staging, so nothing unreviewed is played.
    """
    try:
        raw_rows = ADAPTERS[source.kind](source)[:importer.MAX_ROWS]
    except SourceError as e:
        source.last_error, source.last_run_at = str(e), timezone.now()
        source.save(update_fields=["last_error", "last_run_at", "updated_at"])
        raise
    results, warnings = importer.validate(source.card_type, raw_rows)
    now = timezone.now()
    record = CardImport.objects.create(
        card_type=source.card_type, file_name=f"{source.name} · {timezone.localtime(now):%d.%m.%Y %H:%M}",
        uploaded_by=user, source=source, rows=importer.to_json(results), file_warnings=warnings,
        summary=importer.summarize(results))
    if auto_apply:
        record.result = importer.apply(source.card_type, record.rows)
        record.status, record.applied_at = CardImport.Status.APPLIED, timezone.now()
        record.save(update_fields=["result", "status", "applied_at", "updated_at"])
    source.last_error, source.last_run_at = "", now
    source.save(update_fields=["last_error", "last_run_at", "updated_at"])
    return record
