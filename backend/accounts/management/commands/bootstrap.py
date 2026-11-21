from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from accounts.models import ClientApp


class Command(BaseCommand):
    help = (
        "Set up / refresh the backbone data on a server. Safe to run any number of times (after every deploy):\n"
        "  1. client apps from settings.CLIENT_APPS (create or update name, allow_guests)\n"
        "  2. legal texts from legal_texts/<app>/ (privacy policy, KVKK) -> a new version only if a text changed\n"
        "Example: python manage.py bootstrap"
    )

    def handle(self, *args, **options):
        for slug, config in settings.CLIENT_APPS.items():
            app, created = ClientApp.objects.update_or_create(
                slug=slug, defaults={"name": config["name"], "allow_guests": config.get("allow_guests", False)}
            )
            self.stdout.write(self.style.MIGRATE_HEADING(f"[{slug}] client app {'created' if created else 'ok'}"))

            if (Path(settings.BASE_DIR) / "legal_texts" / slug).is_dir():
                call_command("publish_legal_documents", slug, stdout=self.stdout)
            else:
                self.stdout.write(self.style.WARNING(f"  no legal_texts/{slug}/ folder: legal texts skipped"))

        self.stdout.write(self.style.SUCCESS("Bootstrap finished."))
        if not (settings.LEGAL_CONTROLLER_NAME and settings.LEGAL_CONTACT_EMAIL):
            self.stdout.write(self.style.WARNING(
                "LEGAL_CONTROLLER_NAME / LEGAL_CONTACT_EMAIL are empty in .env: the published pages show placeholders."
            ))
