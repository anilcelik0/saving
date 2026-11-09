from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from saving_budget.services import create_default_categories
from saving_budget.signals import SAVING_APP_SLUG


class Command(BaseCommand):
    help = "Add missing default categories to all saving users (idempotent; existing categories are kept)."

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(app__slug=SAVING_APP_SLUG)
        for user in users:
            create_default_categories(user)
        self.stdout.write(self.style.SUCCESS(f"Default categories ensured for {users.count()} saving user(s)."))
