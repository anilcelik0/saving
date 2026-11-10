"""
Read-only reports over saving_budget and saving_invest data. Month scope follows the monthly summary: card transactions
count in their account's statement cycle, everything else in the calendar month; cancelled rows never count.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import reduce
from operator import or_

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from saving_budget.models import Account, Category, Kind, Transaction
from saving_budget.services import month_bounds, month_scope
from saving_invest.models import AssetPrice, Deposit, Trade
from saving_invest.services import _replay, deposit_value

ZERO = Decimal("0")
CENT = Decimal("0.01")
MONEY_FIELD = DecimalField(max_digits=20, decimal_places=2)
COUNTED = ~Q(status=Transaction.Status.CANCELLED)


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def pct(part, whole):
    return (Decimal(part) / Decimal(whole) * 100).quantize(CENT, rounding=ROUND_HALF_UP) if whole else None


def _total(**filters):
    return Coalesce(Sum("amount", filter=Q(**filters)), Value(ZERO), output_field=MONEY_FIELD)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def month_list(end_year: int, end_month: int, months: int) -> list[tuple[int, int]]:
    """`months` consecutive (year, month) pairs ending with the given month, oldest first."""
    return [shift_month(end_year, end_month, -i) for i in range(months - 1, -1, -1)]


def period_scope(user, months: list[tuple[int, int]]) -> Q:
    return reduce(or_, (month_scope(user, y, m)[0] for y, m in months))


def _label(months):
    (y1, m1), (y2, m2) = months[0], months[-1]
    return {"start_month": f"{y1:04d}-{m1:02d}", "end_month": f"{y2:04d}-{m2:02d}", "months": len(months)}


# ---------------------------------------------------------------- category breakdown
def category_breakdown(user, kind: str, end_year: int, end_month: int, months: int) -> dict:
    """Totals per category in the period, share of the total and change vs. the preceding period of the same length."""
    current = month_list(end_year, end_month, months)
    previous = month_list(*shift_month(*current[0], -1), months)
    base = Transaction.objects.filter(COUNTED, user=user, kind=kind)

    def grouped(period):
        rows = base.filter(period_scope(user, period)).values("category").annotate(amount=Sum("amount"), count=Count("id"))
        return {r["category"]: r for r in rows}

    now, before = grouped(current), grouped(previous)
    names = dict(Category.objects.filter(user=user).values_list("id", "name"))
    total = sum((r["amount"] for r in now.values()), ZERO)
    previous_total = sum((r["amount"] for r in before.values()), ZERO)
    items = []
    for category_id in set(now) | set(before):
        amount = now.get(category_id, {}).get("amount", ZERO)
        prev = before.get(category_id, {}).get("amount", ZERO)
        items.append({
            "category": category_id, "name": names.get(category_id, "Kategorisiz"),
            "amount": money(amount), "count": now.get(category_id, {}).get("count", 0),
            "pct": pct(amount, total), "previous": money(prev), "change_pct": pct(amount - prev, prev),
        })
    items.sort(key=lambda i: (-i["amount"], -i["previous"], i["name"]))
    return {
        "kind": kind, "period": _label(current), "previous_period": _label(previous),
        "total": money(total), "previous_total": money(previous_total),
        "change_pct": pct(total - previous_total, previous_total), "items": items,
    }


def category_transactions(user, kind: str, category_id, end_year: int, end_month: int, months: int):
    """Transactions behind one breakdown row (category_id None = uncategorized)."""
    qs = Transaction.objects.select_related("series").filter(
        COUNTED, period_scope(user, month_list(end_year, end_month, months)), user=user, kind=kind)
    qs = qs.filter(category__isnull=True) if category_id is None else qs.filter(category_id=category_id)
    return qs.order_by("-date", "-created_at")


# ---------------------------------------------------------------- monthly trend
def monthly_trend(user, end_year: int, end_month: int, months: int) -> dict:
    """
    Per month: income, expense, net (as in the summary) + investment flows (purchases/deposits out, reductions/
    closings in). Saving = (income - investment in) - (expense - investment out); saving rate is its share of income.
    """
    base = Transaction.objects.filter(COUNTED, user=user)
    rows = []
    for y, m in month_list(end_year, end_month, months):
        t = base.filter(month_scope(user, y, m)[0]).aggregate(
            income=_total(kind=Kind.INCOME), expense=_total(kind=Kind.EXPENSE),
            investment_in=_total(kind=Kind.INCOME, source=Transaction.Source.INVESTMENT),
            investment_out=_total(kind=Kind.EXPENSE, source=Transaction.Source.INVESTMENT),
        )
        earned = t["income"] - t["investment_in"]
        saving = earned - (t["expense"] - t["investment_out"])
        rows.append({
            "month": f"{y:04d}-{m:02d}", "income": money(t["income"]), "expense": money(t["expense"]),
            "net": money(t["income"] - t["expense"]), "investment_out": money(t["investment_out"]),
            "investment_in": money(t["investment_in"]), "saving": money(saving), "saving_rate": pct(saving, earned),
        })
    active = [r for r in rows if r["income"] or r["expense"]] or rows  # months before the user started don't dilute
    averages = {k: money(sum((r[k] for r in active), ZERO) / len(active))
                for k in ("income", "expense", "net", "saving", "investment_out")}
    earned_total = sum((r["income"] - r["investment_in"] for r in active), ZERO)
    averages["saving_rate"] = pct(sum((r["saving"] for r in active), ZERO), earned_total)
    averages["months"] = len(active)
    return {"period": _label(month_list(end_year, end_month, months)), "months": rows, "averages": averages}


# ---------------------------------------------------------------- wealth (net worth + portfolio history)
def _cash_at(user, accounts, on: date) -> Decimal:
    """Account balances as of `on`: opening balance + paid in-balance movements paid on or before that day."""
    paid = Transaction.objects.filter(
        user=user, account__in=accounts, status=Transaction.Status.PAID, in_balance=True,
    ).filter(Q(paid_on__lte=on) | Q(paid_on__isnull=True, date__lte=on)).aggregate(
        income=_total(kind=Kind.INCOME), expense=_total(kind=Kind.EXPENSE))
    return sum((a.opening_balance for a in accounts), ZERO) + paid["income"] - paid["expense"]


def _price_on(asset_id, on: date):
    return AssetPrice.objects.filter(asset_id=asset_id, date__lte=on).order_by("-date").values_list("buy", flat=True).first()


def _deposit_alive(deposit: Deposit, on: date) -> bool:
    if deposit.start_date > on:
        return False
    if deposit.status == Deposit.Status.CLOSED:
        return deposit.closed_on is None or deposit.closed_on > on
    if deposit.status == Deposit.Status.RENEWED:
        return deposit.maturity_date > on  # the renewal takes over from the maturity date
    return True


def wealth_history(user, end_year: int, end_month: int, months: int) -> dict:
    """
    Month-end (today for the current month) snapshots: cash in accounts, holdings at that day's latest buy price
    (at cost when no price was stored yet -> `priced` false), deposits with interest accrued so far, net worth.
    """
    today = timezone.localdate()
    accounts = list(Account.objects.filter(user=user, is_archived=False))
    trades = list(Trade.objects.filter(user=user).select_related("asset"))
    deposits = list(Deposit.objects.filter(user=user))
    points = []
    for y, m in month_list(end_year, end_month, months):
        on = min(month_bounds(y, m)[1], today)
        if date(y, m, 1) > today:
            break
        assets_value = assets_cost = ZERO
        priced = True
        for position in _replay([t for t in trades if t.date <= on]).values():
            if position.quantity <= 0:
                continue
            price = _price_on(position.asset.pk, on)
            priced = priced and price is not None
            assets_cost += position.cost
            assets_value += position.quantity * price if price is not None else position.cost
        alive = [d for d in deposits if _deposit_alive(d, on)]
        deposits_value = sum((deposit_value(d, on) for d in alive), ZERO)
        deposits_principal = sum((d.principal for d in alive), ZERO)
        cash = _cash_at(user, accounts, on)
        investments = money(assets_value) + deposits_value
        points.append({
            "month": f"{y:04d}-{m:02d}", "date": on, "cash": money(cash),
            "assets_value": money(assets_value), "assets_cost": money(assets_cost),
            "deposits_value": money(deposits_value), "deposits_principal": money(deposits_principal),
            "investments": money(investments),
            "investments_gain": money(investments - assets_cost - deposits_principal),
            "net_worth": money(cash + investments), "priced": priced,
        })
    first, last = (points[0], points[-1]) if points else (None, None)
    change = money(last["net_worth"] - first["net_worth"]) if points else ZERO
    return {
        "period": _label(month_list(end_year, end_month, months)), "points": points,
        "net_worth_change": change, "net_worth_change_pct": pct(change, first["net_worth"]) if points else None,
    }
