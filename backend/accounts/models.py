import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from core.base_models import TimeStampedModel

username_validator = RegexValidator(
    regex=r"^[a-z0-9_.-]{3,30}$",
    message="Kullanıcı adı 3-30 karakter olmalı; yalnızca küçük harf, rakam, '_', '.' ve '-' içerebilir.",
)


class ClientApp(TimeStampedModel):
    """A client application served by this backend (e.g. 'saving')."""

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.slug


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError("Username is required.")
        if not email:
            raise ValueError("Email is required.")
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email, password=None, app=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, app=app, **extra_fields)

    def create_superuser(self, username, email, password=None, **extra_fields):
        """Platform admins are not bound to any client app (app=NULL)."""
        extra_fields.update(is_staff=True, is_superuser=True)
        return self._create_user(username, email, password, app=None, **extra_fields)

    def get_by_natural_key(self, username):
        # Natural key lookups (createsuperuser, admin) target platform accounts only.
        return self.get(username=username.strip().lower(), app__isnull=True)


class User(AbstractBaseUser, PermissionsMixin):
    """
    App-scoped account: the same email/username may exist once per ClientApp,
    each with its own password. app=NULL means a platform (admin) account.
    """

    class AccountStatus(models.TextChoices):
        ACTIVE = "active", "Aktif"
        DEACTIVATED = "deactivated", "Dondurulmuş"
        DELETION_PENDING = "deletion_pending", "Silinmeyi bekliyor"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    app = models.ForeignKey(
        ClientApp, on_delete=models.PROTECT, null=True, blank=True, related_name="users"
    )
    # Self-service lifecycle (accounts.lifecycle). Login still works so the user can reopen / cancel deletion;
    # client app APIs refuse non-active accounts (AppPermission).
    account_status = models.CharField(max_length=20, choices=AccountStatus.choices, default=AccountStatus.ACTIVE)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    delete_after = models.DateTimeField(null=True, blank=True, help_text="Permanent deletion time (deletion_pending)")
    username = models.CharField(max_length=30, validators=[username_validator])
    email = models.EmailField(max_length=254)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["app", "username"], name="uniq_username_per_app", nulls_distinct=False
            ),
            models.UniqueConstraint(
                fields=["app", "email"], name="uniq_email_per_app", nulls_distinct=False
            ),
        ]

    def __str__(self):
        return f"{self.username}@{self.app_id and self.app.slug or 'platform'}"

    def save(self, *args, **kwargs):
        self.username = self.username.strip().lower()
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class LegalDocument(TimeStampedModel):
    """
    Versioned legal text of a client app (privacy policy, KVKK information notice), Markdown with placeholders
    filled at render time (see accounts.legal). A published version is immutable: changes go into a new version,
    which users must accept again.
    """

    class Kind(models.TextChoices):
        PRIVACY = "privacy", "Gizlilik Politikası"
        KVKK = "kvkk", "KVKK Aydınlatma Metni"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    app = models.ForeignKey(ClientApp, on_delete=models.PROTECT, related_name="legal_documents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    version = models.PositiveIntegerField(editable=False)
    title = models.CharField(max_length=150)
    body = models.TextField(
        help_text="Markdown. Placeholders: {{controller}}, {{email}}, {{app}}, {{version}}, {{date}}"
    )
    requires_acceptance = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True, help_text="Empty = draft (not shown to users)")

    class Meta:
        ordering = ["app", "kind", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["app", "kind", "version"], name="uniq_legal_document_version"),
        ]

    def __str__(self):
        return f"{self.app_id and self.app.slug}/{self.kind} v{self.version}"

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    def save(self, *args, **kwargs):
        if self._state.adding and not self.version:
            last = LegalDocument.objects.filter(app=self.app, kind=self.kind).aggregate(v=models.Max("version"))["v"]
            self.version = (last or 0) + 1
        super().save(*args, **kwargs)


class LegalAcceptance(models.Model):
    """Proof that a user accepted a specific legal document version (time, IP, client)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="legal_acceptances")
    document = models.ForeignKey(LegalDocument, on_delete=models.PROTECT, related_name="acceptances")
    accepted_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-accepted_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "document"], name="uniq_legal_acceptance"),
        ]

    def __str__(self):
        return f"{self.user} accepted {self.document}"
