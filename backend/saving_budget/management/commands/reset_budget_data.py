from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from saving_budget.models import (
    Account, Category, MerchantCategoryRule, Series, StatementImport, Transaction,
)
from saving_budget.services import create_default_categories
from saving_budget.signals import SAVING_APP_SLUG


class Command(BaseCommand):
    help = (
        "DELETE all saving_budget data (statements, transactions, series, learned rules, accounts, categories) "
        "for every user, then re-create default categories. User accounts are kept. Requires --yes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirm the deletion.")

    @transaction.atomic
    def handle(self, *args, yes=False, **options):
        if not yes:
            raise CommandError("This deletes all budget data. Re-run with --yes to confirm.")
        for statement in StatementImport.objects.exclude(file=""):
            statement.file.delete(save=False)
        counts = {
            "statements": StatementImport.objects.all().delete()[0],
            "transactions": Transaction.objects.all().delete()[0],
            "series": Series.objects.all().delete()[0],
            "rules": MerchantCategoryRule.objects.all().delete()[0],
            "accounts": Account.objects.all().delete()[0],
            "categories": Category.objects.all().delete()[0],
        }
        users = get_user_model().objects.filter(app__slug=SAVING_APP_SLUG)
        for user in users:
            create_default_categories(user)
        self.stdout.write(self.style.SUCCESS(
            "Deleted: " + ", ".join(f"{k}={v}" for k, v in counts.items())
            + f". Default categories re-created for {users.count()} user(s)."
        ))
