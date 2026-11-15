from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import IssueAttachment, IssueReport


@shared_task
def purge_issue_attachments() -> int:
    """
    Delete attachment files (screenshots, statements) of resolved/closed reports and any older than
    ISSUE_ATTACHMENT_RETENTION_DAYS. The rows stay (name, size, deleted_at) as a record. Returns files removed.
    """
    now = timezone.now()
    cutoff = now - timedelta(days=settings.ISSUE_ATTACHMENT_RETENTION_DAYS)
    done = [IssueReport.Status.RESOLVED, IssueReport.Status.CLOSED]
    removed = 0
    for attachment in (IssueAttachment.objects.filter(deleted_at__isnull=True).exclude(file="")
                       .filter(Q(created_at__lt=cutoff) | Q(report__status__in=done))):
        attachment.file.delete(save=False)
        attachment.deleted_at = now
        attachment.save(update_fields=["file", "deleted_at", "updated_at"])
        removed += 1
    return removed
