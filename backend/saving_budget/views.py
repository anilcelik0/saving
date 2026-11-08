from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.viewsets import OwnedModelViewSet

from .models import Account, Category, GoalContribution, RecurringPayment, SavingGoal, Transaction
from .permissions import IsSavingUser
from .serializers import (
    AccountSerializer,
    CategorySerializer,
    GoalContributionSerializer,
    PayRecurringSerializer,
    RecurringPaymentSerializer,
    SavingGoalSerializer,
    TransactionSerializer,
)
from .services import pay_recurring


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
        qs = super().get_queryset()
        if self.request.query_params.get("include_archived") != "true":
            qs = qs.filter(is_archived=False)
        return qs


class TransactionViewSet(SavingViewSet):
    """Filters: date_from, date_to, kind, category, account, source, search."""

    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if date_from := _query_date(self.request, "date_from"):
            qs = qs.filter(date__gte=date_from)
        if date_to := _query_date(self.request, "date_to"):
            qs = qs.filter(date__lte=date_to)
        for field in ("kind", "category", "account", "source"):
            if value := params.get(field):
                qs = qs.filter(**{field: value})
        if search := params.get("search"):
            qs = qs.filter(description__icontains=search)
        return qs


class RecurringPaymentViewSet(SavingViewSet):
    queryset = RecurringPayment.objects.all()
    serializer_class = RecurringPaymentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if (active := self.request.query_params.get("is_active")) in ("true", "false"):
            qs = qs.filter(is_active=active == "true")
        return qs

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        """Active payments due within `days` (default 30), including overdue ones."""
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            raise ValidationError({"days": "Gün sayısı tam sayı olmalı."})
        until = timezone.localdate() + timedelta(days=days)
        qs = self.get_queryset().filter(is_active=True, next_due_date__lte=until)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        serializer = PayRecurringSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = pay_recurring(
            self.get_object(),
            amount=serializer.validated_data.get("amount"),
            paid_on=serializer.validated_data.get("date"),
        )
        return Response(TransactionSerializer(txn, context={"request": request}).data, status=status.HTTP_201_CREATED)


class SavingGoalViewSet(SavingViewSet):
    queryset = SavingGoal.objects.all()
    serializer_class = SavingGoalSerializer

    def get_queryset(self):
        qs = super().get_queryset().annotate(
            current_amount=Coalesce(
                Sum("contributions__amount"), Value(Decimal("0")), output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        )
        if status_param := self.request.query_params.get("status"):
            qs = qs.filter(status=status_param)
        return qs


class GoalContributionViewSet(SavingViewSet):
    queryset = GoalContribution.objects.select_related("goal")
    serializer_class = GoalContributionSerializer
    owner_field = "goal__user"

    def get_queryset(self):
        qs = super().get_queryset()
        if goal := self.request.query_params.get("goal"):
            qs = qs.filter(goal=goal)
        return qs
