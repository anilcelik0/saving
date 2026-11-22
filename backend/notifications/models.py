from django.conf import settings
from django.db import models

from core.base_models import BaseModel


class DeviceToken(BaseModel):
    """An FCM registration token of a signed-in device. A token belongs to the user who registered it last."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_tokens")
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=20, default="android")
    last_seen = models.DateTimeField()

    class Meta:
        ordering = ["-last_seen"]
        verbose_name = "cihaz"
        verbose_name_plural = "cihazlar"

    def __str__(self):
        return f"{self.user} · {self.platform} · …{self.token[-8:]}"
