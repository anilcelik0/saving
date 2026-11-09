from django.core.management.base import BaseCommand

from saving_budget.models import Account, StatementImport, StatementLine, Transaction
from saving_budget.statements.registry import BANK_LABELS


class Command(BaseCommand):
    help = (
        "Mark transactions imported from card statements as is_card and fill statement_day / card_name of their "
        "accounts (for data imported before card cycles existed). Idempotent."
    )

    def handle(self, *args, **options):
        card_lines = StatementLine.objects.filter(
            statement__statement_type=StatementImport.StatementType.CARD, result_transaction__isnull=False
        )
        flagged = Transaction.objects.filter(
            pk__in=card_lines.values("result_transaction"), is_card=False
        ).update(is_card=True)

        accounts = 0
        for statement in StatementImport.objects.filter(
            statement_type=StatementImport.StatementType.CARD, status=StatementImport.Status.IMPORTED
        ).select_related("account").order_by("created_at"):
            account: Account = statement.account
            fields = []
            if not account.statement_day and statement.period_end:
                account.statement_day = statement.period_end.day
                fields.append("statement_day")
            if not account.card_name:
                account.card_name = f"{BANK_LABELS.get(statement.bank, account.name)} Kredi Kartı"[:60]
                fields.append("card_name")
            if fields:
                account.save(update_fields=fields)
                accounts += 1
        self.stdout.write(self.style.SUCCESS(f"{flagged} transaction(s) flagged as card, {accounts} account(s) updated."))
