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

from .models import Account, Category, MerchantCategoryRule, Series, StatementImport, StatementLine, Transaction
from .permissions import IsSavingUser
from .serializers import (
    AccountSerializer,
    CategorySerializer,
    BulkStatusSerializer,
    CycleSerializer,
    MerchantCategoryRuleSerializer,
    MonthlySummarySerializer,
    PaySerializer,
    SeriesSerializer,
    StatementImportSerializer,
    StatementLineSerializer,
    TransactionCreateSerializer,
    TransactionSerializer,
    serialize_activity,
)
from .services import (
    activity_month, activity_upcoming, apply_to_following, bulk_set_status, cancel_transaction, card_cycle_q,
    delete_cycle, delete_with_following, learn_category, mark_paid, mark_unpaid, monthly_summary,
    restore_transaction, sync_auto_pay_status, with_balance,
)
from .statement_services import confirm_statement, delete_statement_data
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
        if self.action == "list" and self.request.query_params.get("include_archived") != "true":
            qs = qs.filter(is_archived=False)  # archived rows stay reachable by id (edit, un-archive, delete)
        return qs


class AccountViewSet(SavingViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    pagination_class = None

    def get_queryset(self):
        qs = with_balance(super().get_queryset())
        if self.action == "list" and self.request.query_params.get("include_archived") != "true":
            qs = qs.filter(is_archived=False)  # archived rows stay reachable by id (edit, un-archive, delete)
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
        for field in ("kind", "category", "account", "source", "series"):
            if value := params.get(field):
                qs = qs.filter(**{field: value})
        if (is_card := params.get("is_card")) in ("true", "false"):
            qs = qs.filter(is_card=is_card == "true")
        # card cycle of an account (same rule as summaries): ?account=..&cycle_start=..&cycle_end=..
        cycle_start, cycle_end = _query_date(self.request, "cycle_start"), _query_date(self.request, "cycle_end")
        if cycle_start and cycle_end and (account := params.get("account")):
            qs = qs.filter(card_cycle_q(account, cycle_start, cycle_end))
        if status_param := params.get("status"):  # "paid" or "paid,cancelled"
            qs = qs.filter(status__in=status_param.split(","))
        if search := params.get("search"):
            qs = qs.filter(description__icontains=search)
        if params.get("ordering") == "date":
            qs = qs.order_by("date", "created_at")
        return qs

    def perform_update(self, serializer):
        scope = _scope(self.request)
        old_category_id = serializer.instance.category_id
        old_due = (serializer.instance.date, serializer.instance.auto_pay)
        txn = serializer.save()
        if (txn.date, txn.auto_pay) != old_due:
            sync_auto_pay_status(txn)
        if scope == "following":
            apply_to_following(txn, serializer.validated_data)
        if txn.category_id != old_category_id and txn.description:
            learn_category(txn.user, txn.kind, txn.description, txn.category)

    @action(detail=False, methods=["post"], url_path="bulk-status")
    def bulk_status(self, request):
        """Mark a card cycle (account + date range) as paid or unpaid in one go."""
        serializer = BulkStatusSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        updated = bulk_set_status(request.user, **serializer.validated_data)
        return Response({"updated": updated})

    @action(detail=False, methods=["post"], url_path="delete-cycle")
    def delete_cycle(self, request):
        """Delete a whole card cycle (account + date range), e.g. a statement imported to the wrong card."""
        serializer = CycleSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response({"deleted": delete_cycle(request.user, **serializer.validated_data)})

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a purchase (e.g. refunded) or skip a planned occurrence. Kept in history, excluded from totals."""
        txn = cancel_transaction(self.get_object())
        return Response(TransactionSerializer(txn, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        txn = restore_transaction(self.get_object())
        return Response(TransactionSerializer(txn, context={"request": request}).data)

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
        """Body: {"delete_after": true} removes the statement record and lines after importing (transactions stay)."""
        statement = confirm_statement(self.get_object())
        data = dict(self.get_serializer(statement).data, deleted=False)
        if str(request.data.get("delete_after", "")).lower() in ("true", "1"):
            delete_statement_data(statement)
            data["deleted"] = True
        return Response(data)

    def perform_destroy(self, instance):
        delete_statement_data(instance)


class SeriesViewSet(SavingViewSet):
    """GET: recurring/installment payments with their next pending occurrence (?active=false for all)."""

    queryset = Series.objects.prefetch_related("transactions__series")
    serializer_class = SeriesSerializer
    pagination_class = None
    http_method_names = ["get"]

    def get_queryset(self):
        qs = super().get_queryset().order_by("description")
        if self.request.query_params.get("active", "true") == "true":
            qs = qs.filter(is_active=True, transactions__status=Transaction.Status.PENDING).distinct()
        return qs


class MerchantCategoryRuleViewSet(SavingViewSet):
    """Learned merchant -> category rules: list and delete (rules are created by the user's category choices)."""

    queryset = MerchantCategoryRule.objects.select_related("category")
    serializer_class = MerchantCategoryRuleSerializer
    pagination_class = None
    http_method_names = ["get", "delete"]


class StatementLineViewSet(SavingViewSet):
    """Review a preview line: action (import/match/skip), category, matched_transaction."""

    queryset = StatementLine.objects.select_related("statement", "matched_transaction")
    serializer_class = StatementLineSerializer
    owner_field = "statement__user"
    http_method_names = ["patch"]


def _query_month(request):
    raw = request.query_params.get("month")
    today = timezone.localdate()
    try:
        year, month = (int(p) for p in raw.split("-")) if raw else (today.year, today.month)
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        raise ValidationError({"month": "Ay YYYY-AA formatında olmalı."})
    return year, month


class SummaryView(APIView):
    """GET ?month=YYYY-MM (default: current month)."""

    permission_classes = [IsSavingUser]

    def get(self, request):
        year, month = _query_month(request)
        return Response(MonthlySummarySerializer(monthly_summary(request.user, year, month)).data)


class ActivityView(APIView):
    """
    GET ?month=YYYY-MM -> history items (same scope as the summary), newest first:
      {"type": "transaction", "transaction": {...}} for non-card movements,
      {"type": "card_cycle", ...} one row per card statement cycle of each account.
    """

    permission_classes = [IsSavingUser]

    def get(self, request):
        year, month = _query_month(request)
        return Response(serialize_activity(activity_month(request.user, year, month), {"request": request}))


class ActivityUpcomingView(APIView):
    """GET ?days=30 -> pending items (non-card one by one, card ones grouped per cycle), oldest first."""

    permission_classes = [IsSavingUser]

    def get(self, request):
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError:
            raise ValidationError({"days": "Gün sayısı tam sayı olmalı."})
        return Response(serialize_activity(activity_upcoming(request.user, days), {"request": request}))
