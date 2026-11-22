from django.urls import path

from .views import ChallengeAcceptView, ChallengeDetailView, ChallengeListView, ChallengeSendView

app_name = "lineup_social"

urlpatterns = [
    path("challenges/", ChallengeListView.as_view(), name="challenges"),
    path("challenges/<str:code>/", ChallengeDetailView.as_view(), name="challenge-detail"),
    path("challenges/<str:code>/accept/", ChallengeAcceptView.as_view(), name="challenge-accept"),
    path("challenges/<str:code>/send/", ChallengeSendView.as_view(), name="challenge-send"),
]
