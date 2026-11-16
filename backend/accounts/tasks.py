from celery import shared_task
from django.core.management import call_command


@shared_task
def delete_scheduled_accounts() -> int:
    """Permanently delete accounts whose deletion grace period is over."""
    from .lifecycle import delete_due_accounts

    return delete_due_accounts()


@shared_task
def flush_expired_tokens():
    """Remove expired outstanding/blacklisted refresh tokens."""
    call_command("flushexpiredtokens")
