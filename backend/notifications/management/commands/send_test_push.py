from django.core.management.base import BaseCommand, CommandError

from notifications import fcm


class Command(BaseCommand):
    help = (
        "Send a test push through a client's Firebase project. Default target: topic '<app>-dev', which debug builds "
        "subscribe to. Example: python manage.py send_test_push lineup --title Merhaba --body 'Test bildirimi'"
    )

    def add_arguments(self, parser):
        parser.add_argument("app", help="Client app slug (key file: secrets/firebase-<app>.json)")
        parser.add_argument("--topic", help="Default: <app>-dev")
        parser.add_argument("--token", help="A single device token instead of a topic")
        parser.add_argument("--title", default="Test bildirimi")
        parser.add_argument("--body", default="Sunucudan gönderildi.")

    def handle(self, app, topic=None, token=None, title="", body="", **options):
        if not token and not topic:
            topic = f"{app}-dev"
        try:
            message_id = fcm.send(app, title, body, token=token, topic=None if token else topic)
        except fcm.FCMNotConfigured as e:
            raise CommandError(str(e)) from None
        self.stdout.write(self.style.SUCCESS(f"Sent to {'token' if token else 'topic ' + topic}: {message_id}"))
