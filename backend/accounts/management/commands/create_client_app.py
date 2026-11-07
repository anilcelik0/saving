from django.core.management.base import BaseCommand

from accounts.models import ClientApp


class Command(BaseCommand):
    help = "Create (or update the name of) a client application. Example: create_client_app saving Saving"

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("name")

    def handle(self, *args, slug, name, **options):
        app, created = ClientApp.objects.update_or_create(slug=slug, defaults={"name": name})
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} client app: {app.slug}"))
