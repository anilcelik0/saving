from rest_framework.routers import DefaultRouter

from . import views

app_name = "saving_budget"

router = DefaultRouter()
router.register("categories", views.CategoryViewSet)
router.register("accounts", views.AccountViewSet)
router.register("transactions", views.TransactionViewSet)
router.register("recurring-payments", views.RecurringPaymentViewSet)
router.register("goals", views.SavingGoalViewSet)
router.register("goal-contributions", views.GoalContributionViewSet)

urlpatterns = router.urls
