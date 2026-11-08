import logging

from celery import shared_task

from .services import process_due_plans

logger = logging.getLogger(__name__)


@shared_task
def process_due_plans_task():
    """Daily: create transactions for due auto-pay plan occurrences."""
    created = process_due_plans()
    logger.info("Auto-pay plans processed, %s transaction(s) created.", created)
    return created
