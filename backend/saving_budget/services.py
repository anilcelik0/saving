import calendar
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction as db_transaction
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Account, Category, Kind, MerchantCategoryRule, Series, Transaction

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
PAID, PENDING, CANCELLED = Transaction.Status.PAID, Transaction.Status.PENDING, Transaction.Status.CANCELLED

HORIZON_DAYS = 365  # recurring series are generated this far ahead
EXTEND_THRESHOLD_DAYS = 60  # extend when fewer days than this remain generated

# Fields that "this and following" edits propagate across a series.
SERIES_SHARED_FIELDS = ("amount", "description", "category", "account", "auto_pay", "is_card", "note")

DEFAULT_CATEGORIES = {
    Kind.EXPENSE: [
        "Market", "Yeme-İçme", "Faturalar", "Kira", "Ulaşım", "Sağlık", "Eğitim", "Giyim", "Eğlence",
        "Abonelikler", "Online Alışveriş", "Ev & Elektronik", "Kişisel Bakım", "Para Transferi", "Nakit Çekim",
        "Banka Masrafı", "Kredi/Borç", "Yatırım", "Diğer Gider",
    ],
    Kind.INCOME: ["Maaş", "Ek Gelir", "Gelen Transfer", "İade", "Faiz/Getiri", "Yatırım", "Diğer Gelir"],
}
FALLBACK_CATEGORY = {Kind.EXPENSE: "Diğer Gider", Kind.INCOME: "Diğer Gelir"}


def create_default_categories(user):
    Category.objects.bulk_create(
        [Category(user=user, kind=kind, name=name) for kind, names in DEFAULT_CATEGORIES.items() for name in names],
        ignore_conflicts=True,
    )


def ensure_category(user, kind: str, name: str) -> Category:
    return Category.objects.filter(user=user, kind=kind, name__iexact=name).first() or         Category.objects.create(user=user, kind=kind, name=name)


def sync_linked_entry(entry, *, user, account, kind, amount, date, description, category_name="Yatırım"):
    """
    Keep one paid transaction mirroring a movement from another feature (e.g. an investment buy).
    No account or amount -> the mirror is removed. Returns the transaction or None.
    """
    if account is None or not amount:
        if entry is not None:
            entry.delete()
        return None
    if entry is None:
        entry = Transaction(user=user, source=Transaction.Source.INVESTMENT,
                            category=ensure_category(user, kind, category_name))
    entry.kind, entry.amount, entry.account, entry.description = kind, amount, account, description
    entry.date, entry.paid_on, entry.status = date, date, Transaction.Status.PAID
    entry.save()
    return entry


def _sum(**filters):
    return Coalesce(Sum("amount", filter=Q(**filters)), Value(ZERO), output_field=MONEY_FIELD)


# ---------------------------------------------------------------- balances
def with_balance(queryset):
    """Annotate accounts with `balance` = opening_balance + paid income - paid expense (history-only rows excluded)."""

    def paid_total(kind):
        sub = (
            Transaction.objects.filter(account=OuterRef("pk"), kind=kind, status=PAID, in_balance=True)
            .values("account")
            .annotate(s=Sum("amount"))
            .values("s")
        )
        return Coalesce(Subquery(sub, output_field=MONEY_FIELD), Value(ZERO), output_field=MONEY_FIELD)

    return queryset.annotate(_income=paid_total(Kind.INCOME), _expense=paid_total(Kind.EXPENSE)).annotate(
        balance=F("opening_balance") + F("_income") - F("_expense")
    )


# ---------------------------------------------------------------- schedule math
def add_months(d: date, months: int, anchor_day: int) -> date:
    """Add months keeping the original day where possible (Jan 31 -> Feb 28 -> Mar 31)."""
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def next_occurrence(series: Series, current: date) -> date:
    step = series.interval
    if series.frequency == Series.Frequency.WEEKLY:
        return current + timedelta(weeks=step)
    months = step if series.frequency == Series.Frequency.MONTHLY else 12 * step
    return add_months(current, months, series.start_date.day)


def split_installments(total: Decimal, count: int) -> tuple[Decimal, Decimal]:
    """Return (base share, last share); rounding remainder goes to the last installment."""
    base = (total / count).quantize(CENT, rounding=ROUND_DOWN)
    return base, total - base * (count - 1)


def _occurrence_amount(series: Series, sequence: int) -> Decimal:
    if series.series_type == Series.SeriesType.INSTALLMENT and sequence == series.installment_count:
        return split_installments(series.total_amount, series.installment_count)[1]
    return series.amount


def generate_occurrences(series: Series, until: date) -> list[Transaction]:
    """Create pending transactions for the series up to `until` (respects end_date/installment_count)."""
    sequence = series.generated_count
    due = series.start_date if sequence == 0 else next_occurrence(series, series.generated_until)
    rows = []
    while due <= until:
        if series.installment_count and sequence >= series.installment_count:
            break
        if series.end_date and due > series.end_date:
            break
        sequence += 1
        rows.append(
            Transaction(
                user=series.user, kind=series.kind, amount=_occurrence_amount(series, sequence), date=due,
                status=PENDING, auto_pay=series.auto_pay, is_card=series.is_card,
                description=series.description, note=series.note,
                category=series.category, account=series.account, series=series, sequence=sequence,
            )
        )
        series.generated_count, series.generated_until = sequence, due
        due = next_occurrence(series, due)
    if rows:
        Transaction.objects.bulk_create(rows)
        series.save(update_fields=["generated_count", "generated_until", "updated_at"])
    return rows


# ---------------------------------------------------------------- daily maintenance
def settle_auto_pay(today: date | None = None, **filters) -> int:
    """Mark due auto-pay pending transactions as paid on their date."""
    today = today or timezone.localdate()
    return Transaction.objects.filter(status=PENDING, auto_pay=True, date__lte=today, **filters).update(
        status=PAID, paid_on=F("date"), updated_at=timezone.now()
    )


def extend_series(today: date | None = None) -> int:
    """Top up open-ended recurring series that have less than EXTEND_THRESHOLD_DAYS generated ahead."""
    today = today or timezone.localdate()
    qs = Series.objects.filter(
        series_type=Series.SeriesType.RECURRING,
        is_active=True,
        generated_until__lt=today + timedelta(days=EXTEND_THRESHOLD_DAYS),
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=F("generated_until")))
    created = 0
    for series in qs:
        created += len(generate_occurrences(series, today + timedelta(days=HORIZON_DAYS)))
    return created


# ---------------------------------------------------------------- entry lifecycle
@db_transaction.atomic
def create_entry(*, user, repeat: str, data: dict, series_options: dict) -> Transaction:
    """
    Single entry point. repeat: 'none' | 'recurring' | 'installment'.
    For installment, data['amount'] is the TOTAL amount. Returns the first created transaction.
    """
    today = timezone.localdate()
    if repeat == "none":
        is_paid = data["date"] <= today
        return Transaction.objects.create(
            user=user, status=PAID if is_paid else PENDING, paid_on=data["date"] if is_paid else None, **data
        )

    total = data["amount"] if repeat == Series.SeriesType.INSTALLMENT else None
    count = series_options.get("installment_count") if total else None
    series = Series.objects.create(
        user=user,
        series_type=repeat,
        frequency=series_options.get("frequency", Series.Frequency.MONTHLY),
        interval=series_options.get("interval", 1),
        start_date=data["date"],
        end_date=None if total else series_options.get("end_date"),
        installment_count=count,
        total_amount=total,
        kind=data["kind"],
        amount=split_installments(total, count)[0] if total else data["amount"],
        description=data.get("description", ""),
        category=data.get("category"),
        account=data["account"],
        auto_pay=data.get("auto_pay", False),
        is_card=data.get("is_card", False),
        note=data.get("note", ""),
    )
    until = date.max if total else max(series.start_date, today) + timedelta(days=HORIZON_DAYS)
    rows = generate_occurrences(series, until)
    settle_auto_pay(today, series=series)
    return Transaction.objects.get(pk=rows[0].pk)


def mark_paid(txn: Transaction, *, amount=None, paid_on=None) -> Transaction:
    if txn.status == PAID:
        raise ValidationError({"detail": "Bu kayıt zaten ödendi olarak işaretli."})
    txn.status = PAID
    txn.paid_on = paid_on or timezone.localdate()
    if amount:
        txn.amount = amount
    txn.save(update_fields=["status", "paid_on", "amount", "updated_at"])
    return txn


def cancel_transaction(txn: Transaction) -> Transaction:
    """Cancel (refunded purchase / skipped occurrence). Kept for history, excluded from balances and totals."""
    if txn.status == CANCELLED:
        raise ValidationError({"detail": "Bu kayıt zaten iptal edilmiş."})
    txn.status, txn.paid_on = CANCELLED, None
    txn.save(update_fields=["status", "paid_on", "updated_at"])
    return txn


def restore_transaction(txn: Transaction) -> Transaction:
    if txn.status != CANCELLED:
        raise ValidationError({"detail": "Bu kayıt iptal edilmemiş."})
    is_paid = txn.date <= timezone.localdate()
    txn.status, txn.paid_on = (PAID, txn.date) if is_paid else (PENDING, None)
    txn.save(update_fields=["status", "paid_on", "updated_at"])
    return txn


def learn_category(user, kind: str, description: str, category) -> str | None:
    """Remember merchant -> category from a user's choice. Returns the merchant key (or None)."""
    from .statements.classify import merchant_key

    key = merchant_key(description)
    if not key or category is None:
        return None
    MerchantCategoryRule.objects.update_or_create(
        user=user, kind=kind, merchant_key=key, defaults={"category": category}
    )
    return key


def mark_unpaid(txn: Transaction) -> Transaction:
    if txn.status == PENDING:
        raise ValidationError({"detail": "Bu kayıt zaten bekliyor durumunda."})
    txn.status, txn.paid_on = PENDING, None
    txn.save(update_fields=["status", "paid_on", "updated_at"])
    return txn


def _following_pending(txn: Transaction):
    return Transaction.objects.filter(series=txn.series, status=PENDING, date__gt=txn.date)


@db_transaction.atomic
def apply_to_following(txn: Transaction, changes: dict):
    """Propagate shared-field changes to later pending occurrences and the series template."""
    changes = {k: v for k, v in changes.items() if k in SERIES_SHARED_FIELDS}
    if not changes or txn.series_id is None:
        return
    _following_pending(txn).update(**changes, updated_at=timezone.now())
    Series.objects.filter(pk=txn.series_id).update(**changes, updated_at=timezone.now())


@db_transaction.atomic
def delete_with_following(txn: Transaction):
    """Delete this occurrence and later pending ones; stop the series. Paid history is kept."""
    if txn.series_id:
        _following_pending(txn).delete()
        Series.objects.filter(pk=txn.series_id).update(is_active=False, updated_at=timezone.now())
    txn.delete()


# ---------------------------------------------------------------- summary
def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _cut_off(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def card_cycle(year: int, month: int, statement_day: int) -> tuple[date, date]:
    """Card statement cycle counted in (year, month): day after previous cut-off .. this month's cut-off.
    statement_day=15, Feb 2026 -> (2026-01-16, 2026-02-15)."""
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    return _cut_off(prev_year, prev_month, statement_day) + timedelta(days=1), _cut_off(year, month, statement_day)


def card_cycle_q(account_id, start: date, end: date) -> Q:
    """Card transactions of an account in cycle [start, end]: statement imports by the statement's cut-off
    (cycle_end, exactly as the bank billed them), others (manual/pending) by their own date."""
    return Q(is_card=True, account_id=account_id) & (
        Q(cycle_end__range=(start, end)) | Q(cycle_end__isnull=True, date__range=(start, end))
    )


def month_scope(user, year: int, month: int):
    """
    Q for transactions counted in a summary month + the card cycles used.
    Non-card transactions: calendar month. Card transactions: their account's statement cycle
    (accounts without a statement day fall back to the calendar month). Each account is evaluated on its own.
    """
    start, end = month_bounds(year, month)
    scope = Q(is_card=False, date__range=(start, end))
    cycles = []
    for account_id, name, day in Account.objects.filter(user=user).values_list("id", "name", "statement_day"):
        if day:
            cycle_start, cycle_end = card_cycle(year, month, day)
            cycles.append({"account": account_id, "name": name, "start": cycle_start, "end": cycle_end})
        else:
            cycle_start, cycle_end = start, end
        scope |= card_cycle_q(account_id, cycle_start, cycle_end)
    return scope, cycles


def monthly_summary(user, year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    today = timezone.localdate()
    txns = Transaction.objects.filter(user=user)
    scope, cycles = month_scope(user, year, month)

    m = txns.filter(scope).aggregate(
        income_paid=_sum(kind=Kind.INCOME, status=PAID),
        income_pending=_sum(kind=Kind.INCOME, status=PENDING),
        expense_paid=_sum(kind=Kind.EXPENSE, status=PAID),
        expense_pending=_sum(kind=Kind.EXPENSE, status=PENDING),
    )
    overdue = txns.filter(status=PENDING, in_balance=True, date__lt=today).aggregate(
        income=_sum(kind=Kind.INCOME), expense=_sum(kind=Kind.EXPENSE)
    )
    accounts = list(with_balance(Account.objects.filter(user=user, is_archived=False)))
    current_balance = sum((a.balance for a in accounts), ZERO)

    projected = None
    if end >= today:  # all pending up to month end (incl. overdue) assumed to happen
        upto = txns.filter(status=PENDING, in_balance=True, date__lte=end).aggregate(
            income=_sum(kind=Kind.INCOME), expense=_sum(kind=Kind.EXPENSE)
        )
        projected = current_balance + upto["income"] - upto["expense"]

    income = m["income_paid"] + m["income_pending"]
    expense = m["expense_paid"] + m["expense_pending"]
    return {
        "month": f"{year:04d}-{month:02d}",
        "income": income,
        "income_paid": m["income_paid"],
        "income_pending": m["income_pending"],
        "expense": expense,
        "expense_paid": m["expense_paid"],
        "expense_pending": m["expense_pending"],
        "net": income - expense,
        "accounts": [{"id": a.id, "name": a.name, "account_type": a.account_type, "balance": a.balance} for a in accounts],
        "card_cycles": cycles,
        "current_balance": current_balance,
        "overdue_income": overdue["income"],
        "overdue_expense": overdue["expense"],
        "projected_balance": projected,
    }


# ---------------------------------------------------------------- activity feed (account-based history)
def cycle_containing(d: date, statement_day: int | None) -> tuple[date, date]:
    """Card cycle (or calendar month when no statement day) that contains date d."""
    if not statement_day:
        return month_bounds(d.year, d.month)
    if d <= _cut_off(d.year, d.month, statement_day):
        return card_cycle(d.year, d.month, statement_day)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return card_cycle(year, month, statement_day)


def _cycle_item(account, start, end, txns) -> dict:
    active = [t for t in txns if t.status != CANCELLED]
    statuses = {t.status for t in active}
    if not active:
        status = "cancelled"
    elif statuses == {PAID}:
        status = "paid"
    elif statuses == {PENDING}:
        status = "pending"
    else:
        status = "partial"
    expense = sum((t.amount for t in active if t.kind == Kind.EXPENSE), ZERO)
    income = sum((t.amount for t in active if t.kind == Kind.INCOME), ZERO)
    pending = sum((t.amount if t.kind == Kind.EXPENSE else -t.amount for t in active if t.status == PENDING), ZERO)
    return {
        "type": "card_cycle", "date": end, "account": account.id, "account_name": account.name,
        "card_name": account.card_name or f"{account.name} kartı",
        "statement_day": account.statement_day, "start": start, "end": end, "count": len(txns),
        "expense": expense, "income": income, "net": income - expense, "pending_amount": pending,
        "status": status, "in_balance": all(t.in_balance for t in txns),
    }


def activity_month(user, year: int, month: int) -> list[dict]:
    """
    Movements of a month, same scope as the summary: non-card transactions one by one (paid, pending,
    cancelled), card transactions grouped per account statement cycle. Newest first.
    """
    start, end = month_bounds(year, month)
    items = [
        {"type": "transaction", "date": t.date, "transaction": t}
        for t in Transaction.objects.filter(user=user, is_card=False, date__range=(start, end)).select_related("series")
    ]
    for account in Account.objects.filter(user=user):
        cycle_start, cycle_end = card_cycle(year, month, account.statement_day) if account.statement_day else (start, end)
        txns = list(Transaction.objects.filter(card_cycle_q(account.id, cycle_start, cycle_end)))
        if txns:
            items.append(_cycle_item(account, cycle_start, cycle_end, txns))
    return sorted(items, key=lambda i: (i["date"], i["type"] == "card_cycle"), reverse=True)


def activity_upcoming(user, days: int = 30) -> list[dict]:
    """Pending within `days` (incl. overdue), oldest first: non-card one by one, card ones grouped per cycle."""
    until = timezone.localdate() + timedelta(days=days)
    pending = Transaction.objects.filter(
        user=user, status=PENDING, in_balance=True, date__lte=until
    ).select_related("series", "account")
    items, groups = [], {}
    for t in pending:
        if t.is_card:
            cycle = cycle_containing(t.cycle_end or t.date, t.account.statement_day)
            groups.setdefault((t.account, cycle), []).append(t)
        else:
            items.append({"type": "transaction", "date": t.date, "transaction": t})
    for (account, (cycle_start, cycle_end)), _ in groups.items():
        cycle_txns = list(Transaction.objects.filter(card_cycle_q(account.id, cycle_start, cycle_end)))
        items.append(_cycle_item(account, cycle_start, cycle_end, cycle_txns))
    return sorted(items, key=lambda i: i["date"])


def bulk_set_status(user, *, account, date_from, date_to, status, paid_on=None) -> int:
    """Mark all card transactions of an account in a cycle as paid / pending (cancelled ones untouched)."""
    qs = Transaction.objects.filter(card_cycle_q(account.id, date_from, date_to), user=user).exclude(status=CANCELLED)
    if status == PAID:
        return qs.filter(status=PENDING).update(status=PAID, paid_on=paid_on or timezone.localdate(),
                                                 updated_at=timezone.now())
    return qs.filter(status=PAID).update(status=PENDING, paid_on=None, updated_at=timezone.now())
