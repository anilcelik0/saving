import calendar
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction as db_transaction
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Account, Category, Kind, PaymentPlan, Transaction

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)

DEFAULT_CATEGORIES = {
    Kind.EXPENSE: [
        "Market", "Faturalar", "Kira", "Ulaşım", "Yeme-İçme", "Sağlık",
        "Eğitim", "Giyim", "Eğlence", "Abonelikler", "Kredi/Borç", "Diğer Gider",
    ],
    Kind.INCOME: ["Maaş", "Ek Gelir", "Faiz/Getiri", "Diğer Gelir"],
}


def create_default_categories(user):
    Category.objects.bulk_create(
        [Category(user=user, kind=kind, name=name) for kind, names in DEFAULT_CATEGORIES.items() for name in names],
        ignore_conflicts=True,
    )


# ---------------------------------------------------------------- balances
def with_balance(queryset):
    """Annotate accounts with `balance` = opening_balance + income - expense."""

    def total(kind):
        sub = (
            Transaction.objects.filter(account=OuterRef("pk"), kind=kind)
            .values("account")
            .annotate(s=Sum("amount"))
            .values("s")
        )
        return Coalesce(Subquery(sub, output_field=MONEY_FIELD), Value(ZERO), output_field=MONEY_FIELD)

    return queryset.annotate(_income=total(Kind.INCOME), _expense=total(Kind.EXPENSE)).annotate(
        balance=F("opening_balance") + F("_income") - F("_expense")
    )


# ---------------------------------------------------------------- schedule math
def add_months(d: date, months: int, anchor_day: int) -> date:
    """Add months keeping the original day where possible (Jan 31 -> Feb 28 -> Mar 31)."""
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def next_occurrence(plan: PaymentPlan, current: date) -> date:
    step = plan.interval
    if plan.frequency == PaymentPlan.Frequency.WEEKLY:
        return current + timedelta(weeks=step)
    months = step if plan.frequency == PaymentPlan.Frequency.MONTHLY else 12 * step
    return add_months(current, months, plan.start_date.day)


def split_installments(total: Decimal, count: int) -> tuple[Decimal, Decimal]:
    """Return (base share, last share); rounding remainder goes to the last installment."""
    base = (total / count).quantize(CENT, rounding=ROUND_DOWN)
    return base, total - base * (count - 1)


def occurrence_amount(plan: PaymentPlan, sequence: int) -> Decimal:
    if plan.plan_type == PaymentPlan.PlanType.INSTALLMENT and sequence == plan.installment_count:
        return split_installments(plan.total_amount, plan.installment_count)[1]
    return plan.amount


def iter_occurrences(plan: PaymentPlan, until: date):
    """Yield (sequence, due_date, amount) of unpaid occurrences up to `until` (inclusive)."""
    sequence, due = plan.paid_count + 1, plan.next_due_date
    while plan.is_active and due <= until:
        if plan.installment_count and sequence > plan.installment_count:
            return
        if plan.end_date and due > plan.end_date:
            return
        yield sequence, due, occurrence_amount(plan, sequence)
        sequence, due = sequence + 1, next_occurrence(plan, due)


# ---------------------------------------------------------------- plan lifecycle
@db_transaction.atomic
def create_plan(**data) -> PaymentPlan:
    if data["plan_type"] == PaymentPlan.PlanType.INSTALLMENT:
        data["amount"], _ = split_installments(data["total_amount"], data["installment_count"])
        data["end_date"] = None
    data["next_due_date"] = data["start_date"]
    plan = PaymentPlan.objects.create(**data)
    if plan.auto_pay:
        process_plan(plan.pk)
        plan.refresh_from_db()
    return plan


def _record_occurrence(plan: PaymentPlan, *, amount=None, paid_on=None) -> Transaction:
    """Create the next occurrence's transaction and advance the plan. Caller must hold a row lock."""
    sequence = plan.paid_count + 1
    txn = Transaction.objects.create(
        user=plan.user,
        kind=plan.kind,
        amount=amount or occurrence_amount(plan, sequence),
        date=paid_on or plan.next_due_date,
        description=plan.description,
        category=plan.category,
        account=plan.account,
        source=Transaction.Source.PLAN,
        plan=plan,
        plan_sequence=sequence,
    )
    plan.paid_count = sequence
    plan.next_due_date = next_occurrence(plan, plan.next_due_date)
    installments_done = plan.installment_count and plan.paid_count >= plan.installment_count
    past_end = plan.end_date and plan.next_due_date > plan.end_date
    if installments_done or past_end:
        plan.is_active = False
    plan.save(update_fields=["paid_count", "next_due_date", "is_active", "updated_at"])
    return txn


@db_transaction.atomic
def pay_plan(plan: PaymentPlan, *, amount=None, paid_on=None) -> Transaction:
    """User marks the next occurrence as paid (default date: today)."""
    plan = PaymentPlan.objects.select_for_update().get(pk=plan.pk)
    if not plan.is_active:
        raise ValidationError({"detail": "Bu ödeme planı aktif değil."})
    return _record_occurrence(plan, amount=amount, paid_on=paid_on or timezone.localdate())


def process_plan(plan_id, today: date | None = None) -> int:
    """Create transactions for all due occurrences of an auto-pay plan (catches up missed days)."""
    today = today or timezone.localdate()
    created = 0
    while True:
        with db_transaction.atomic():
            plan = PaymentPlan.objects.select_for_update().get(pk=plan_id)
            if not (plan.is_active and plan.auto_pay and plan.next_due_date <= today):
                return created
            _record_occurrence(plan)
            created += 1


def process_due_plans(today: date | None = None) -> int:
    today = today or timezone.localdate()
    ids = PaymentPlan.objects.filter(is_active=True, auto_pay=True, next_due_date__lte=today).values_list("id", flat=True)
    return sum(process_plan(plan_id, today) for plan_id in ids)


# ---------------------------------------------------------------- summary
def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def monthly_summary(user, year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    today = timezone.localdate()

    totals = Transaction.objects.filter(user=user, date__range=(start, end)).aggregate(
        income=Coalesce(Sum("amount", filter=Q(kind=Kind.INCOME)), Value(ZERO), output_field=MONEY_FIELD),
        expense=Coalesce(Sum("amount", filter=Q(kind=Kind.EXPENSE)), Value(ZERO), output_field=MONEY_FIELD),
    )

    accounts = list(with_balance(Account.objects.filter(user=user, is_archived=False)))
    total_balance = sum((a.balance for a in accounts), ZERO)

    # Pending plan occurrences until month end (includes overdue unpaid ones). Only meaningful for current/future months.
    planned = {Kind.INCOME: ZERO, Kind.EXPENSE: ZERO}
    if end >= today:
        for plan in PaymentPlan.objects.filter(user=user, is_active=True, next_due_date__lte=end):
            for _, _, amount in iter_occurrences(plan, end):
                planned[plan.kind] += amount

    return {
        "month": f"{year:04d}-{month:02d}",
        "income": totals["income"],
        "expense": totals["expense"],
        "net": totals["income"] - totals["expense"],
        "accounts": [
            {"id": a.id, "name": a.name, "account_type": a.account_type, "balance": a.balance} for a in accounts
        ],
        "total_balance": total_balance,
        "planned_income": planned[Kind.INCOME],
        "planned_expense": planned[Kind.EXPENSE],
        "projected_balance": total_balance + planned[Kind.INCOME] - planned[Kind.EXPENSE],
    }
