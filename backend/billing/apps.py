from django.apps import AppConfig


def _delete_user_billing_data(user) -> None:
    """Account deletion: store events keep the user id in their payload, so they go too (the rest cascades)."""
    from .models import StoreEvent

    StoreEvent.objects.filter(user=user).delete()


class BillingConfig(AppConfig):
    name = "billing"
    verbose_name = "Ödüller ve abonelikler"

    def ready(self):
        from accounts.lifecycle import register_user_data_cleanup

        register_user_data_cleanup(_delete_user_billing_data)
