import logging

from celery import shared_task
from firebase_admin import exceptions, messaging

from . import fcm
from .models import DeviceToken

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def send_push(user_id: str, title: str, body: str, data: dict) -> int:
    """Send to each device token of the user; tokens FCM no longer knows are removed. Returns the number sent."""
    sent = 0
    for device in DeviceToken.objects.filter(user_id=user_id).select_related("user__app"):
        try:
            fcm.send(device.user.app.slug, title, body, token=device.token, data=data)
            sent += 1
        except fcm.FCMNotConfigured as e:
            logger.warning("Push skipped: %s", e)
            return sent
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError):
            device.delete()  # app uninstalled / token rotated
        except exceptions.FirebaseError:
            logger.exception("Push to device %s failed", device.pk)
    return sent
