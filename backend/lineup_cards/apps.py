from django.apps import AppConfig


class LineupCardsConfig(AppConfig):
    name = "lineup_cards"
    verbose_name = "Line Up · Kart havuzu"

    def ready(self):
        from support.registry import register_related_provider

        from .services import card_snapshot

        # "Hata bildir" on a card: the report keeps what the card looked like at that moment
        register_related_provider("lineup.card", card_snapshot)
