from django.apps import AppConfig


class SavingBudgetConfig(AppConfig):
    name = "saving_budget"
    verbose_name = "Saving Budget"

    def ready(self):
        from support.registry import register_related_provider

        from . import signals  # noqa: F401
        from .statement_services import statement_snapshot

        # "Sorun bildir" from a statement: the report keeps what the statement looked like at that moment
        register_related_provider("saving.statement", statement_snapshot)

        # account deletion: transactions/series hold PROTECT links to accounts, so they are removed first
        from accounts.lifecycle import register_user_data_cleanup

        from .services import delete_user_budget_data

        register_user_data_cleanup(delete_user_budget_data)
