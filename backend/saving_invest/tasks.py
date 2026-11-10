import logging

from celery import shared_task

from .services import fetch_prices

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30 * 60)
def fetch_daily_prices(self):
    """Daily: store today's asset prices. Retries (every 30 min, 3 times) if a provider fails."""
    result = fetch_prices()
    logger.info("Prices: %s saved, failed: %s", result["saved"], result["failed"] or "none")
    if result["failed"]:
        raise self.retry(exc=RuntimeError(f"Price fetch failed: {result['failed']}"))
    return result
