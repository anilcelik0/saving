from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.viewsets import OwnedModelViewSet

from .models import Account, Category, PaymentPlan, Transaction
from .permissions import IsSavingUser
from .serializers import (
    AccountSerializer,
    CategorySerializer,
    MonthlySummarySerializer,
    PaymentPlanSerializer,
    PayPlanSerializer,
    TransactionSerializer,
)
from .services import monthly_summary, pay_plan, with_balance


def _query_date(request, name):
    raw = request.query_params.get(name)
    if not raw:
        return None
    value = parse_date(raw)
    if value is None:
        raise ValidationError({name: "Tarih YYYY-AA-GG formatında olmalı."})
    return value


class SavingViewSet(OwnedModelViewSet):
    permission_classes = [IsSavingUser]


class CategoryViewSet(SavingViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        if kind := self.request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        if self.request.query_params.get("include_archived") != "true":
            qs = qs.filter(is_archived=False)
        return qs


class AccountViewSet(SavingViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    pagination_class = None

    def get_queryset(self):
        qs = with_balance(super().get_queryset())
        if self.request.query_params.get("include_archived") != "true":
            qs = qs.filter(is_archived=False)
        return qs

    def perform_create(self, serializer):
        account = serializer.save(user=self.request.user)
        account.balance = account.opening_balance  # new account has no transactions yet

    def perform_update(self, serializer):
        account = serializer.save()
        account.balance = with_balance(Account.objects.filter(pk=account.pk)).get().balance


class TransactionViewSet(SavingViewSet):
    """Filters: date_from, date_to, kind, category, account, source, plan, search."""

    queryset = Transaction.objects.select_related("plan")
    serializer_class = TransactionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if date_from := _query_date(self.request, "date_from"):
            qs = qs.filter(date__gte=date_from)
        if date_to := _query_date(self.request, "date_to"):
            qs = qs.filter(date__lte=date_to)
        for field in ("kind", "category", "account", "source", "plan"):
            if value := params.get(field):
                qs = qs.filter(**{field: value})
        if search := params.get("search"):
            qs = qs.filter(description__icontains=search)
        return qs


class PaymentPlanViewSet(SavingViewSet):
    queryset = PaymentPlan.objects.all()
    serializer_class = PaymentPlanSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (active := params.get("is_active")) in ("true", "false"):
            qs = qs.filter(is_active=active == "true")
        if plan_type := params.get("plan_type"):
            qs = qs.filter(plan_type=plan_type)
        return qs

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        """Active plans due within `days` (default 30), including overdue ones."""
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            raise ValidationError({"days": "Gün sayısı tam sayı olmalı."})
        until = timezone.localdate() + timedelta(days=days)
        qs = self.get_queryset().filter(is_active=True, next_due_date__lte=until)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        serializer = PayPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = pay_plan(
            self.get_object(),
            amount=serializer.validated_data.get("amount"),
            paid_on=serializer.validated_data.get("date"),
        )
        return Response(TransactionSerializer(txn, context={"request": request}).data, status=status.HTTP_201_CREATED)


class SummaryView(APIView):
    """GET ?month=YYYY-MM (default: current month): balances, month totals, pending plan amounts."""

    permission_classes = [IsSavingUser]

    def get(self, request):
        raw = request.query_params.get("month")
        today = timezone.localdate()
        try:
            year, month = (int(p) for p in raw.split("-")) if raw else (today.year, today.month)
            if not 1 <= month <= 12:
                raise ValueError
        except ValueError:
            raise ValidationError({"month": "Ay YYYY-AA formatında olmalı."})
        return Response(MonthlySummarySerializer(monthly_summary(request.user, year, month)).data)
