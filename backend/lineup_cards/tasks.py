import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from .models import CardSource
from .sources import SourceError, run_source

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def fetch_source(source_id: str, user_id: str | None = None) -> None:
    """Admin "Çek": a preview import (applied by hand after review). Errors are kept on the source."""
    source = CardSource.objects.select_related("card_type").get(pk=source_id)
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    try:
        run_source(source, user=user)
    except SourceError:
        logger.warning("Card source %s failed", source.name, exc_info=True)


@shared_task(ignore_result=True)
def refresh_sources() -> None:
    """Monthly (beat): every auto-refresh source; new and changed cards go to staging for review."""
    for source in CardSource.objects.filter(auto_refresh=True).select_related("card_type"):
        try:
            record = run_source(source, auto_apply=True)
            logger.info("Card source %s refreshed: %s", source.name, record.result)
        except SourceError:
            logger.warning("Card source %s failed", source.name, exc_info=True)
