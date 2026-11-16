"""
Self-service account lifecycle: deactivate (freeze), request deletion (grace period), reactivate, and the
permanent deletion run by Celery (accounts.tasks.delete_scheduled_accounts).

Client apps register a cleanup for data whose relations would block a plain cascade (e.g. PROTECT foreign keys)
via register_user_data_cleanup(fn); fn(user) runs inside the deletion transaction before user.delete().
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import User

logger = logging.getLogger(__name__)
Status = User.AccountStatus
_cleanups = []


def register_user_data_cleanup(fn) -> None:
    _cleanups.append(fn)


def revoke_sessions(user) -> None:
    """Blacklist every refresh token of the user: all devices are signed out."""
    for token in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
        BlacklistedToken.objects.get_or_create(token=token)


def _set_status(user, status, delete_after=None):
    user.account_status = status
    user.status_changed_at = timezone.now()
    user.delete_after = delete_after
    user.save(update_fields=["account_status", "status_changed_at", "delete_after"])


@transaction.atomic
def deactivate(user) -> None:
    _set_status(user, Status.DEACTIVATED)
    revoke_sessions(user)


@transaction.atomic
def request_deletion(user) -> None:
    """Locks the account; it is deleted for good after ACCOUNT_DELETION_GRACE_DAYS unless the user cancels."""
    if user.account_status != Status.DELETION_PENDING:
        _set_status(user, Status.DELETION_PENDING,
                    timezone.now() + timedelta(days=settings.ACCOUNT_DELETION_GRACE_DAYS))
    revoke_sessions(user)


def reactivate(user) -> None:
    """Reopen a frozen account or cancel a pending deletion."""
    if user.account_status != Status.ACTIVE:
        _set_status(user, Status.ACTIVE)


@transaction.atomic
def delete_account(user) -> None:
    """Permanent: the user row and everything that belongs to it (client data, consents, reports, files)."""
    for cleanup in _cleanups:
        cleanup(user)
    user.delete()


def delete_due_accounts() -> int:
    due = User.objects.filter(account_status=Status.DELETION_PENDING, delete_after__lte=timezone.now())
    deleted = 0
    for user in due:
        try:
            delete_account(user)
            deleted += 1
        except Exception:  # keep going; the user is retried tomorrow
            logger.exception("Account %s could not be deleted", user.pk)
    return deleted
