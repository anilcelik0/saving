"""
Firebase Cloud Messaging, one Firebase project per client app.

Credentials: service account key at FIREBASE_CREDENTIALS_DIR/firebase-<app slug>.json (never committed; copied to the
server by hand). Device tokens and sends from Celery arrive in Phase 6; for now only direct sends (test command).
"""

from pathlib import Path

import firebase_admin
from django.conf import settings
from firebase_admin import credentials, messaging


class FCMNotConfigured(Exception):
    pass


def _app(slug: str) -> firebase_admin.App:
    """The firebase_admin app of a client, initialized once per process."""
    try:
        return firebase_admin.get_app(slug)
    except ValueError:
        path = Path(settings.FIREBASE_CREDENTIALS_DIR) / f"firebase-{slug}.json"
        if not path.is_file():
            raise FCMNotConfigured(f"No Firebase key for '{slug}': {path}") from None
        return firebase_admin.initialize_app(credentials.Certificate(path), name=slug)


def send(slug: str, title: str, body: str, *, token: str | None = None, topic: str | None = None,
         data: dict[str, str] | None = None) -> str:
    """Send one notification to a device token or a topic; returns the FCM message id."""
    if (token is None) == (topic is None):
        raise ValueError("Give exactly one of token / topic.")
    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        token=token,
        topic=topic,
        android=messaging.AndroidConfig(priority="high"),
    )
    return messaging.send(message, app=_app(slug))
