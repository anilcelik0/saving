from decimal import Decimal

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from saving_budget.models import Kind
from saving_budget.permissions import IsSavingUser
from saving_budget.serializers import TransactionSerializer
from saving_budget.views import _query_month

from .services import category_breakdown, category_transactions, monthly_trend, wealth_history

PERIOD_MONTHS = (1, 3, 6, 12)


def _plain(value):
    """Decimals as strings (API convention for money), recursively."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _months(request, allowed=None, default=1, maximum=24):
    try:
        months = int(request.query_params.get("months", default))
    except ValueError:
        months = 0
    if (allowed and months not in allowed) or not 1 <= months <= maximum:
        options = ", ".join(map(str, allowed)) if allowed else f"1-{maximum}"
        raise ValidationError({"months": f"Ay sayısı şunlardan biri olmalı: {options}."})
    return months


def _kind(request):
    kind = request.query_params.get("kind", Kind.EXPENSE)
    if kind not in Kind.values:
        raise ValidationError({"kind": "Tür 'expense' veya 'income' olmalı."})
    return kind


class CategoryBreakdownView(APIView):
    """GET ?kind=expense|income&month=YYYY-MM (period end, default current)&months=1|3|6|12."""

    permission_classes = [IsSavingUser]

    def get(self, request):
        year, month = _query_month(request)
        data = category_breakdown(request.user, _kind(request), year, month, _months(request, PERIOD_MONTHS))
        return Response(_plain(data))


class CategoryTransactionsView(APIView):
    """GET ?category=<id>|none&kind=&month=&months= -> transactions behind one breakdown row."""

    permission_classes = [IsSavingUser]

    def get(self, request):
        year, month = _query_month(request)
        raw = request.query_params.get("category")
        if not raw:
            raise ValidationError({"category": "Kategori gerekli ('none' = kategorisiz)."})
        qs = category_transactions(request.user, _kind(request), None if raw == "none" else raw, year, month,
                                   _months(request, PERIOD_MONTHS))
        return Response(TransactionSerializer(qs, many=True, context={"request": request}).data)


class TrendView(APIView):
    """GET ?month=YYYY-MM (last month, default current)&months=3..24 (default 12)."""

    permission_classes = [IsSavingUser]

    def get(self, request):
        year, month = _query_month(request)
        return Response(_plain(monthly_trend(request.user, year, month, _months(request, default=12))))


class WealthView(APIView):
    """GET ?month=&months= (default 12) -> month-end net worth: cash + holdings + deposits, investment gain."""

    permission_classes = [IsSavingUser]

    def get(self, request):
        year, month = _query_month(request)
        return Response(_plain(wealth_history(request.user, year, month, _months(request, default=12))))
