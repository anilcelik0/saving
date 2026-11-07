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

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    app = models.ForeignKey(
        ClientApp, on_delete=models.PROTECT, null=True, blank=True, related_name="users"
    )
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
