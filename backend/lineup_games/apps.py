from django.apps import AppConfig


class LineupGamesConfig(AppConfig):
    name = "lineup_games"
    verbose_name = "Line Up · Oyunlar"

    def ready(self):
        from .rewards import register

        # rewarded ads (shared billing app): +1 energy, one continue per run
        register()
