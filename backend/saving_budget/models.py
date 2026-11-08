from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from core.base_models import BaseModel

MONEY = {"max_digits": 14, "decimal_places": 2}
POSITIVE = MinValueValidator(Decimal("0.01"))


class Kind(models.TextChoices):
    INCOME = "income", "Gelir"
    EXPENSE = "expense", "Gider"


class OwnedModel(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True


class Category(OwnedModel):
    name = models.CharField(max_length=50)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    icon = models.CharField(max_length=30, blank=True)
    color = models.CharField(max_length=7, blank=True)  # "#RRGGBB"
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "user", "kind", name="uniq_category_name_per_user_kind"
            ),
        ]

    def __str__(self):
        return self.name


class Account(OwnedModel):
    """
    Balance = opening_balance + paid income - paid expense (computed, never stored).
    No credit card type: card spending is an expense on the related bank account.
    """

    class AccountType(models.TextChoices):
        BANK = "bank", "Banka"
        CASH = "cash", "Nakit"

    name = models.CharField(max_length=50)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.BANK)
    opening_balance = models.DecimalField(**MONEY, default=Decimal("0"))
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Series(OwnedModel):
    """
    Internal repeat rule that groups and generates Transactions (never shown as a separate screen).
    Installment: all occurrences generated at creation.
    Recurring: generated ~12 months ahead; a daily task extends open-ended series.
    Template fields (kind..note) are used for occurrences generated later.
    """

    class SeriesType(models.TextChoices):
        RECURRING = "recurring", "Düzenli"
        INSTALLMENT = "installment", "Taksitli"

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Haftalık"
        MONTHLY = "monthly", "Aylık"
        YEARLY = "yearly", "Yıllık"

    series_type = models.CharField(max_length=12, choices=SeriesType.choices)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
    interval = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    installment_count = models.PositiveSmallIntegerField(null=True, blank=True)
    total_amount = models.DecimalField(**MONEY, null=True, blank=True)
    is_active = models.BooleanField(default=True)  # False = stopped, no more generation
    generated_count = models.PositiveSmallIntegerField(default=0)
    generated_until = models.DateField(null=True, blank=True)  # date of the last generated occurrence

    # template for future occurrences
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(**MONEY)
    description = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    auto_pay = models.BooleanField(default=False)
    note = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "series"
        indexes = [models.Index(fields=["series_type", "is_active", "generated_until"])]

    def __str__(self):
        return self.description


class Transaction(OwnedModel):
    """
    The single money-movement model. `date` = when it happens (due date for future ones).
    Only PAID transactions affect balances; PENDING ones are planned/upcoming (overdue if date < today).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Bekliyor"
        PAID = "paid", "Ödendi"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manuel"
        STATEMENT = "statement", "Ekstre"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(**MONEY, validators=[POSITIVE])
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PAID)
    paid_on = models.DateField(null=True, blank=True)
    auto_pay = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    series = models.ForeignKey(Series, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions")
    sequence = models.PositiveSmallIntegerField(null=True, blank=True)  # n-th occurrence in series

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "-date"]),
            models.Index(fields=["user", "status", "date"]),
            models.Index(fields=["status", "auto_pay", "date"]),
            models.Index(fields=["account", "status", "kind"]),
        ]

    def __str__(self):
        return f"{self.date} {self.kind} {self.amount} ({self.status})"
