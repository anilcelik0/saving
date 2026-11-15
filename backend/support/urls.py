from django.urls import path

from .views import IssueReportView

app_name = "support"

urlpatterns = [
    path("issues/", IssueReportView.as_view(), name="issues"),
]
