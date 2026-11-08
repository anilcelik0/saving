import calendar
from datetime import date, timedelta

from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Category, Kind, RecurringPayment, Transaction

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


def add_months(d: date, months: int, anchor_day: int) -> date:
    """Add months keeping the original day where possible (Jan 31 -> Feb 28 -> Mar 31)."""
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def next_occurrence(payment: RecurringPayment, current: date) -> date:
    step = payment.interval
    if payment.frequency == RecurringPayment.Frequency.WEEKLY:
        return current + timedelta(weeks=step)
    months = step if payment.frequency == RecurringPayment.Frequency.MONTHLY else 12 * step
    return add_months(current, months, payment.start_date.day)


@db_transaction.atomic
def pay_recurring(payment: RecurringPayment, *, amount=None, paid_on=None) -> Transaction:
    """Record a payment as an expense transaction and advance the schedule."""
    payment = RecurringPayment.objects.select_for_update().get(pk=payment.pk)
    if not payment.is_active:
        raise ValidationError({"detail": "Bu düzenli ödeme aktif değil."})

    txn = Transaction.objects.create(
        user=payment.user,
        kind=Kind.EXPENSE,
        amount=amount or payment.amount,
        date=paid_on or timezone.localdate(),
        description=payment.name,
        category=payment.category,
        account=payment.account,
        source=Transaction.Source.RECURRING,
        recurring_payment=payment,
    )

    payment.paid_count += 1
    payment.next_due_date = next_occurrence(payment, payment.next_due_date)
    installments_done = payment.installment_count and payment.paid_count >= payment.installment_count
    past_end = payment.end_date and payment.next_due_date > payment.end_date
    if installments_done or past_end:
        payment.is_active = False
    payment.save(update_fields=["paid_count", "next_due_date", "is_active", "updated_at"])
    return txn
