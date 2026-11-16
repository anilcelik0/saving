from django.core.management.base import BaseCommand, CommandError

from accounts import lifecycle
from accounts.models import User


class Command(BaseCommand):
    help = (
        "Delete a user account of a client app. Default: deletion request (locked now, deleted after the grace "
        "period, like the app). --now: permanent deletion right away with all data (e.g. a KVKK request by e-mail). "
        "Example: delete_account saving someuser --now"
    )

    def add_arguments(self, parser):
        parser.add_argument("app", help="client app slug, e.g. saving")
        parser.add_argument("identifier", help="username or e-mail")
        parser.add_argument("--now", action="store_true", help="delete permanently right away (cannot be undone)")

    def handle(self, app, identifier, now=False, **options):
        identifier = identifier.strip().lower()
        field = "email" if "@" in identifier else "username"
        user = User.objects.filter(app__slug=app, **{field: identifier}).first()
        if user is None:
            raise CommandError(f"No {app} user with {field} '{identifier}'.")
        if now:
            lifecycle.delete_account(user)
            self.stdout.write(self.style.WARNING(f"{identifier}: deleted permanently with all data."))
        else:
            lifecycle.request_deletion(user)
            self.stdout.write(self.style.SUCCESS(
                f"{identifier}: deletion requested, locked; deleted after {user.delete_after:%d.%m.%Y}."))
