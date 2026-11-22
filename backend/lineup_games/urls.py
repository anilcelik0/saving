from django.urls import path

from .views import DailyAttemptView, DailyView, HomeView, RunDetailView, RunListView, RunMoveView

app_name = "lineup_games"

urlpatterns = [
    path("home/", HomeView.as_view(), name="home"),
    path("daily/", DailyView.as_view(), name="daily"),
    path("daily/attempts/", DailyAttemptView.as_view(), name="daily-attempts"),
    path("runs/", RunListView.as_view(), name="runs"),
    path("runs/<uuid:pk>/", RunDetailView.as_view(), name="run-detail"),
    path("runs/<uuid:pk>/moves/", RunMoveView.as_view(), name="run-moves"),
]
