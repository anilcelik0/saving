from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "saving_budget"

router = DefaultRouter()
router.register("categories", views.CategoryViewSet)
router.register("accounts", views.AccountViewSet)
router.register("transactions", views.TransactionViewSet)
router.register("statements", views.StatementImportViewSet)
router.register("statement-lines", views.StatementLineViewSet)
router.register("category-rules", views.MerchantCategoryRuleViewSet)

urlpatterns = [
    path("summary/", views.SummaryView.as_view(), name="summary"),
    *router.urls,
]
