"""Push to a user's devices: queued after the current transaction commits, sent by Celery (tasks.send_push)."""

from django.db import transaction
from django.utils import timezone

from .models import DeviceToken


def register_device(user, token: str, platform: str = "android") -> DeviceToken:
    """Upsert: a token moves to the user who registers it now (another account signed in on that phone)."""
    device, _ = DeviceToken.objects.update_or_create(
        token=token, defaults={"user": user, "platform": platform, "last_seen": timezone.now()})
    return device


def unregister_device(user, token: str) -> None:
    DeviceToken.objects.filter(user=user, token=token).delete()


def notify(user, title: str, body: str, data: dict | None = None) -> None:
    """
    Push to every device of the user (only active accounts of an app). `data` values become strings; the client
    reads e.g. {"type": "challenge", "code": "..."} to open the right screen.
    """
    if not user.app_id or user.account_status != user.AccountStatus.ACTIVE:
        return
    payload = {k: str(v) for k, v in (data or {}).items()}
    from .tasks import send_push

    transaction.on_commit(lambda: send_push.delay(str(user.pk), title, body, payload))
