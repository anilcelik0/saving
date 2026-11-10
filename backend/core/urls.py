from django.contrib import admin
from django.urls import include, path

from .views import health

api_v1 = [
    path("health/", health, name="health"),
    path("auth/", include("accounts.urls")),
    path("saving/budget/", include("saving_budget.urls")),
    path("saving/invest/", include("saving_invest.urls")),
    path("saving/reports/", include("saving_reports.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
]
