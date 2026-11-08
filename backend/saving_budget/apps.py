from django.apps import AppConfig


class SavingBudgetConfig(AppConfig):
    name = "saving_budget"
    verbose_name = "Saving Budget"

    def ready(self):
        from . import signals  # noqa: F401
