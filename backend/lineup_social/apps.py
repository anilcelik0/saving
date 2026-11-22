from django.apps import AppConfig


class LineupSocialConfig(AppConfig):
    name = "lineup_social"
    verbose_name = "Line Up · Meydan okumalar"

    def ready(self):
        from lineup_games.signals import run_finished

        from .services import on_run_finished

        run_finished.connect(on_run_finished, dispatch_uid="lineup_social.run_finished")
