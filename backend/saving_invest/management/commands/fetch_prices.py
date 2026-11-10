from django.core.management.base import BaseCommand

from saving_invest.services import fetch_prices


class Command(BaseCommand):
    help = "Sync the asset catalog and fetch today's prices now (same as the daily celery-beat task)."

    def handle(self, *args, **options):
        result = fetch_prices()
        self.stdout.write(f"Saved {result['saved']} price(s). Failed: {result['failed'] or 'none'}")
