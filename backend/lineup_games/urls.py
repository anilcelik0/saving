from django.urls import path

from .views import RunDetailView, RunListView, RunMoveView

app_name = "lineup_games"

urlpatterns = [
    path("runs/", RunListView.as_view(), name="runs"),
    path("runs/<uuid:pk>/", RunDetailView.as_view(), name="run-detail"),
    path("runs/<uuid:pk>/moves/", RunMoveView.as_view(), name="run-moves"),
]
