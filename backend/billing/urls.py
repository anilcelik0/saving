from django.urls import path

from .views import (
    AdMobSSVView, DevEntitlementView, DevGrantView, EntitlementView, RevenueCatWebhookView, RewardIntentDetailView,
    RewardIntentListView,
)

app_name = "billing"

urlpatterns = [
    path("rewards/", RewardIntentListView.as_view(), name="rewards"),
    path("rewards/<uuid:pk>/", RewardIntentDetailView.as_view(), name="reward-detail"),
    path("entitlements/", EntitlementView.as_view(), name="entitlements"),
    path("admob/ssv/", AdMobSSVView.as_view(), name="admob-ssv"),
    path("revenuecat/<slug:app>/", RevenueCatWebhookView.as_view(), name="revenuecat"),
    path("dev/rewards/<uuid:pk>/grant/", DevGrantView.as_view(), name="dev-grant"),
    path("dev/entitlements/", DevEntitlementView.as_view(), name="dev-entitlements"),
]
