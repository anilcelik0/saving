from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.viewsets import OwnedModelViewSet

from .models import Asset, Deposit, Trade
from .permissions import IsSavingUser
from .serializers import (
    AssetPriceSerializer, AssetSerializer, DepositCloseSerializer, DepositRenewSerializer, DepositSerializer,
    PortfolioSerializer, TradeSerializer,
)
from .services import (
    close_deposit, delete_deposit, delete_trade, find_overdraw, latest_prices, portfolio, price_history,
    renew_deposit, reopen_deposit,
)


class AssetViewSet(viewsets.ReadOnlyModelViewSet):
    """GET assets/ (latest price + daily change), assets/{code}/, assets/{code}/history/?days=90."""

    queryset = Asset.objects.filter(is_active=True)
    serializer_class = AssetSerializer
    permission_classes = [IsSavingUser]
    pagination_class = None
    lookup_field = "code"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action in ("list", "retrieve"):
            assets = [self.get_object()] if self.action == "retrieve" else list(self.get_queryset())
            context["prices"] = latest_prices(assets)
        return context

    @action(detail=True, methods=["get"])
    def history(self, request, code=None):
        try:
            days = min(max(int(request.query_params.get("days", 90)), 1), 3650)
        except ValueError:
            raise ValidationError({"days": "Gün sayısı tam sayı olmalı."})
        return Response(AssetPriceSerializer(price_history(self.get_object(), days), many=True).data)


class UserLockedViewSet(OwnedModelViewSet):
    """Writes run in a transaction holding a lock on the user row, so checks over the user's data stay valid."""

    permission_classes = [IsSavingUser]

    def _lock_user(self):
        get_user_model().objects.select_for_update().filter(pk=self.request.user.pk).exists()

    def create(self, request, *args, **kwargs):
        with db_transaction.atomic():
            self._lock_user()
            return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        with db_transaction.atomic():
            self._lock_user()
            return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with db_transaction.atomic():
            self._lock_user()
            return super().destroy(request, *args, **kwargs)


class TradeViewSet(UserLockedViewSet):
    """Purchases and reductions. Filters: asset (code), side. The holding never goes below zero."""

    queryset = Trade.objects.select_related("asset")
    serializer_class = TradeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if asset := self.request.query_params.get("asset"):
            qs = qs.filter(asset__code=asset)
        if side := self.request.query_params.get("side"):
            qs = qs.filter(side=side)
        return qs

    def perform_destroy(self, instance):
        if instance.side == Trade.Side.BUY and find_overdraw(self.request.user, instance.asset, exclude=instance):
            raise ValidationError({"detail": "Bu alış silinirse eldeki miktar eksiye düşer. Önce azaltmaları düzenleyin."})
        delete_trade(instance)


class DepositViewSet(UserLockedViewSet):
    """
    Time deposits (?status=active|renewed|closed). Actions on {id}: close (account?, amount?, date?),
    reopen (undo close), renew (annual_rate, maturity_date, maturity_amount?, name?).
    """

    queryset = Deposit.objects.all()
    serializer_class = DepositSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if status := self.request.query_params.get("status"):
            qs = qs.filter(status__in=status.split(","))
        return qs

    def perform_destroy(self, instance):
        if hasattr(instance, "renewal"):
            raise ValidationError({"detail": "Bu mevduat yenilenmiş. Önce yeni mevduatı silin."})
        delete_deposit(instance)

    def _active(self):
        deposit = self.get_object()
        if deposit.status != Deposit.Status.ACTIVE:
            raise ValidationError({"detail": "Bu işlem yalnızca aktif mevduatta yapılabilir."})
        return deposit

    def _respond(self, deposit):
        return Response(DepositSerializer(deposit, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        deposit = self._active()
        serializer = DepositCloseSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self._respond(close_deposit(deposit, account=data.get("account"), amount=data.get("amount"),
                                           on=data.get("date")))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        deposit = self.get_object()
        if deposit.status != Deposit.Status.CLOSED:
            raise ValidationError({"detail": "Yalnızca kapatılmış mevduat yeniden açılabilir."})
        return self._respond(reopen_deposit(deposit))

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        deposit = self._active()
        serializer = DepositRenewSerializer(data=request.data, context={"deposit": deposit})
        serializer.is_valid(raise_exception=True)
        return self._respond(renew_deposit(deposit, **serializer.validated_data))


class PortfolioView(APIView):
    """GET -> holdings per asset (quantity, average cost, value at latest price, gain) + deposits + totals."""

    permission_classes = [IsSavingUser]

    def get(self, request):
        return Response(PortfolioSerializer(portfolio(request.user)).data)
