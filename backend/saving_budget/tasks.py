import logging

from celery import shared_task

from .services import extend_series, settle_auto_pay

logger = logging.getLogger(__name__)


@shared_task
def daily_budget_maintenance():
    """Daily: mark due auto-pay transactions as paid, then top up open-ended recurring series (12 months ahead)."""
    paid = settle_auto_pay()
    generated = extend_series()
    logger.info("Budget maintenance: %s auto-paid, %s occurrence(s) generated.", paid, generated)
    return {"auto_paid": paid, "generated": generated}
