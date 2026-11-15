import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from accounts.models import ClientApp
from core.base_models import BaseModel


def private_storage():
    from django.core.files.storage import storages

    return storages["private"]


def attachment_upload_path(instance, filename):
    """issue_attachments/<report id>/<random>.<ext> (~75 chars; FileField max_length is 100)."""
    ext = filename.rsplit(".", 1)[-1].lower()[:5] if "." in filename else "bin"
    return f"issue_attachments/{instance.report_id}/{uuid.uuid4().hex[:12]}.{ext}"


class IssueReport(BaseModel):
    """A problem report / suggestion sent from a client app ("Sorun bildir")."""

    class Category(models.TextChoices):
        BUG = "bug", "Hata"
        STATEMENT = "statement", "Ekstre sorunu"
        SUGGESTION = "suggestion", "Öneri"
        OTHER = "other", "Diğer"

    class Status(models.TextChoices):
        NEW = "new", "Yeni"
        IN_PROGRESS = "in_progress", "İnceleniyor"
        RESOLVED = "resolved", "Çözüldü"
        CLOSED = "closed", "Kapatıldı"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="issue_reports")
    app = models.ForeignKey(ClientApp, on_delete=models.PROTECT, related_name="issue_reports")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.BUG)
    message = models.TextField(max_length=4000)
    # technical info sent by the client: app_version, platform, screen, error message
    context = models.JSONField(default=dict, blank=True)
    # optional link to a client-app object, e.g. ("saving.statement", <id>) + a snapshot of it
    related_type = models.CharField(max_length=50, blank=True)
    related_id = models.CharField(max_length=64, blank=True)
    related_snapshot = models.JSONField(default=dict, blank=True)
    attachments_consent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    response = models.TextField(blank=True, help_text="Shown to the user in the app (Bildirimlerim)")
    responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_category_display()} · {self.user} · {self.created_at:%d.%m.%Y}"

    @property
    def is_done(self) -> bool:
        return self.status in (self.Status.RESOLVED, self.Status.CLOSED)


class IssueAttachment(BaseModel):
    """A file sent with a report (screenshot, statement...). The file is removed after the retention period;
    the row stays as a record (name, size, deleted_at)."""

    class Source(models.TextChoices):
        UPLOAD = "upload", "Kullanıcı ekledi"
        STATEMENT = "statement", "Ekstre (cihazdaki son yükleme)"

    report = models.ForeignKey(IssueReport, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_upload_path, storage=private_storage, blank=True)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.UPLOAD)
    deleted_at = models.DateTimeField(null=True, blank=True, help_text="File removed (retention); row kept")

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.original_name


@receiver(post_delete, sender=IssueAttachment)
def _delete_attachment_file(sender, instance, **kwargs):
    """Rows deleted with their report/user (e.g. account deletion) must not leave files behind."""
    if instance.file:
        instance.file.delete(save=False)
