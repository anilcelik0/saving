from datetime import timedelta

from django.db import transaction as db_transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.viewsets import OwnedModelViewSet

from .models import Account, Category, StatementImport, StatementLine, Transaction
from .permissions import IsSavingUser
from .serializers import (
    AccountSerializer,
    CategorySerializer,
    MonthlySummarySerializer,
    PaySerializer,
    StatementImportSerializer,
    StatementLineSerializer,
    TransactionCreateSerializer,
    TransactionSerializer,
)
from .services import apply_to_following, delete_with_following, mark_paid, mark_unpaid, monthly_summary, with_balance
from .statement_services import confirm_statement
from .tasks import parse_statement_task


def _query_date(request, name):
    raw = request.query_params.get(name)
    if not raw:
        return None
    value = parse_date(raw)
    if value is None:
        raise ValidationError({name: "Tarih YYYY-AA-GG formatında olmalı."})
    return value


def _scope(request):
    scope = request.query_params.get("scope", "this")
    if scope not in ("this", "following"):
        raise ValidationError({"scope": "Kapsam 'this' veya 'following' olmalı."})
    return scope


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
    """
    Filters: date_from, date_to, kind, status, category, account, source, series, search; ordering=date|-date.
    Update/delete accept ?scope=this|following for series occurrences.
    """

    queryset = Transaction.objects.select_related("series")

    def get_serializer_class(self):
        return TransactionCreateSerializer if self.action == "create" else TransactionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if date_from := _query_date(self.request, "date_from"):
            qs = qs.filter(date__gte=date_from)
        if date_to := _query_date(self.request, "date_to"):
            qs = qs.filter(date__lte=date_to)
        for field in ("kind", "status", "category", "account", "source", "series"):
            if value := params.get(field):
                qs = qs.filter(**{field: value})
        if search := params.get("search"):
            qs = qs.filter(description__icontains=search)
        if params.get("ordering") == "date":
            qs = qs.order_by("date", "created_at")
        return qs

    def perform_update(self, serializer):
        scope = _scope(self.request)
        txn = serializer.save()
        if scope == "following":
            apply_to_following(txn, serializer.validated_data)

    def perform_destroy(self, instance):
        if _scope(self.request) == "following":
            delete_with_following(instance)
        else:
            instance.delete()

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        """Pending transactions due within `days` (default 30), including overdue ones, oldest first."""
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            raise ValidationError({"days": "Gün sayısı tam sayı olmalı."})
        until = timezone.localdate() + timedelta(days=days)
        qs = (
            Transaction.objects.select_related("series")
            .filter(user=request.user, status=Transaction.Status.PENDING, date__lte=until)
            .order_by("date", "created_at")
        )
        return Response(TransactionSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        serializer = PaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = mark_paid(
            self.get_object(),
            amount=serializer.validated_data.get("amount"),
            paid_on=serializer.validated_data.get("date"),
        )
        return Response(TransactionSerializer(txn, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def unpay(self, request, pk=None):
        txn = mark_unpaid(self.get_object())
        return Response(TransactionSerializer(txn, context={"request": request}).data)


class StatementImportViewSet(SavingViewSet):
    """
    POST (multipart: file, account) -> parsed in background; poll GET until status=ready.
    GET {id}/lines/ -> preview; PATCH statement-lines/{id}/ -> review; POST {id}/confirm/ -> import.
    """

    queryset = StatementImport.objects.select_related("account")
    serializer_class = StatementImportSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "delete"]

    def perform_create(self, serializer):
        statement = serializer.save(user=self.request.user)
        db_transaction.on_commit(lambda: parse_statement_task.delay(str(statement.pk)))

    @action(detail=True, methods=["get"])
    def lines(self, request, pk=None):
        lines = self.get_object().lines.select_related("matched_transaction")
        return Response(StatementLineSerializer(lines, many=True, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        statement = confirm_statement(self.get_object())
        return Response(self.get_serializer(statement).data)


class StatementLineViewSet(SavingViewSet):
    """Review a preview line: action (import/match/skip), category, matched_transaction."""

    queryset = StatementLine.objects.select_related("statement", "matched_transaction")
    serializer_class = StatementLineSerializer
    owner_field = "statement__user"
    http_method_names = ["patch"]


class SummaryView(APIView):
    """GET ?month=YYYY-MM (default: current month)."""

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
