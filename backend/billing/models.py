"""
Rewards for watched ads (granted only after AdMob server-side verification) and store entitlements (e.g. "pro",
kept up to date by RevenueCat webhooks). Shared by every client app; what a reward does is registered by the client
app (billing.registry), so this app never imports client apps.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.base_models import BaseModel


class RewardIntent(BaseModel):
    """
    The client asks for a reward before showing an ad; its id travels as the ad's custom_data and comes back in the
    SSV callback, which grants it once (transaction_id unique).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Bekliyor"
        GRANTED = "granted", "Verildi"
        REJECTED = "rejected", "Reddedildi"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reward_intents")
    kind = models.CharField("tür", max_length=50, help_text='Registered reward, "<app>.<name>" e.g. lineup.energy')
    ref = models.CharField(max_length=64, blank=True, help_text="Object the reward is for (e.g. a run id)")
    status = models.CharField("durum", max_length=10, choices=Status.choices, default=Status.PENDING)
    detail = models.CharField(max_length=200, blank=True, help_text="Why it was rejected")
    transaction_id = models.CharField(max_length=128, null=True, blank=True, unique=True)
    ad_unit = models.CharField(max_length=100, blank=True)
    callback = models.JSONField(default=dict, blank=True, help_text="SSV query parameters (signature dropped)")
    granted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "reklam ödülü"
        verbose_name_plural = "reklam ödülleri"
        indexes = [models.Index(fields=["user", "status", "created_at"], name="billing_intent_user_status")]

    def __str__(self):
        return f"{self.kind} · {self.user} · {self.get_status_display()}"

    @property
    def app_slug(self) -> str:
        return self.kind.split(".", 1)[0]


class Entitlement(BaseModel):
    """A paid feature of a user (e.g. "pro"). Active while expires_at is empty (lifetime) or in the future."""

    class Source(models.TextChoices):
        REVENUECAT = "revenuecat", "RevenueCat"
        ADMIN = "admin", "Yönetici"
        DEV = "dev", "Geliştirme"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entitlements")
    key = models.CharField("hak", max_length=30, default="pro")
    expires_at = models.DateTimeField("bitiş", null=True, blank=True, help_text="Empty = no end")
    source = models.CharField("kaynak", max_length=20, choices=Source.choices, default=Source.ADMIN)
    product_id = models.CharField("ürün", max_length=100, blank=True)
    store = models.CharField("mağaza", max_length=30, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True, help_text="Newest store event applied (older ones are ignored)")

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "abonelik hakkı"
        verbose_name_plural = "abonelik hakları"
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="uniq_billing_entitlement")]

    def __str__(self):
        return f"{self.key} · {self.user}"

    @property
    def is_active(self) -> bool:
        return self.expires_at is None or self.expires_at > timezone.now()


class StoreEvent(BaseModel):
    """Every store webhook received (idempotency by event id + audit)."""

    provider = models.CharField(max_length=20, default="revenuecat")
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=40)
    app_slug = models.CharField(max_length=50)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="+")
    result = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "mağaza olayı"
        verbose_name_plural = "mağaza olayları"

    def __str__(self):
        return f"{self.provider} {self.event_type} · {self.result}"
