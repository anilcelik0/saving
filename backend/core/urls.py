from django.contrib import admin
from django.urls import include, path

from accounts.views import LegalDocumentDetailView, LegalDocumentListView, delete_account_page, legal_page
from support.views import attachment_download

from lineup_social.views import challenge_page

from .views import assetlinks, health

api_v1 = [
    path("health/", health, name="health"),
    path("auth/", include("accounts.urls")),
    path("legal/<slug:app>/", LegalDocumentListView.as_view(), name="legal-list"),
    path("legal/<slug:app>/<slug:kind>/", LegalDocumentDetailView.as_view(), name="legal-detail"),
    path("support/", include("support.urls")),
    path("billing/", include("billing.urls")),
    path("notifications/", include("notifications.urls")),
    path("saving/budget/", include("saving_budget.urls")),
    path("saving/invest/", include("saving_invest.urls")),
    path("saving/reports/", include("saving_reports.urls")),
    path("lineup/games/", include("lineup_games.urls")),
    path("lineup/social/", include("lineup_social.urls")),
]

urlpatterns = [
    # before admin.site.urls so the admin catch-all does not swallow it (staff only)
    path("admin/support/attachment/<uuid:pk>/download/", attachment_download, name="support-attachment-download"),
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    # public web pages (Google Play privacy policy URL etc.)
    path("legal/<slug:app>/<slug:kind>/", legal_page, name="legal-page"),
    path(".well-known/assetlinks.json", assetlinks, name="assetlinks"),
    path("lineup/c/<str:code>", challenge_page, name="lineup-challenge-page"),
    path("account/delete/<slug:app>/", delete_account_page, name="account-delete-page"),
]
