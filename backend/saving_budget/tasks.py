import logging

from celery import shared_task

from .services import extend_series, settle_auto_pay

logger = logging.getLogger(__name__)


@shared_task
def parse_statement_task(statement_id):
    """Parse an uploaded statement into preview lines."""
    from .statement_services import parse_statement

    parse_statement(statement_id)


@shared_task
def daily_budget_maintenance():
    """Daily: mark due auto-pay transactions as paid, then top up open-ended recurring series (12 months ahead)."""
    from .statement_services import cleanup_stale_statement_files

    paid = settle_auto_pay()
    generated = extend_series()
    stale = cleanup_stale_statement_files()
    logger.info("Budget maintenance: %s auto-paid, %s generated, %s stale statement file(s) removed.", paid, generated, stale)
    return {"auto_paid": paid, "generated": generated, "stale_files_removed": stale}
