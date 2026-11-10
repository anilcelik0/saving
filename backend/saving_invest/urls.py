from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AssetViewSet, DepositViewSet, PortfolioView, TradeViewSet

router = DefaultRouter()
router.register("assets", AssetViewSet, basename="asset")
router.register("trades", TradeViewSet, basename="trade")
router.register("deposits", DepositViewSet, basename="deposit")

urlpatterns = [
    path("portfolio/", PortfolioView.as_view(), name="invest-portfolio"),
    *router.urls,
]
