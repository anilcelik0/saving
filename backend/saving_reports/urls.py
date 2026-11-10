from django.urls import path

from .views import CategoryBreakdownView, CategoryTransactionsView, TrendView, WealthView

urlpatterns = [
    path("categories/", CategoryBreakdownView.as_view(), name="report-categories"),
    path("categories/transactions/", CategoryTransactionsView.as_view(), name="report-category-transactions"),
    path("trend/", TrendView.as_view(), name="report-trend"),
    path("wealth/", WealthView.as_view(), name="report-wealth"),
]
