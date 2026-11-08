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
    Balance = opening_balance + income - expense of its transactions (computed, never stored).
    No separate credit card type: card spending is recorded as expense on the related bank account
    (manually or via statement import), so balance means "money available to spend".
    """

    class AccountType(models.TextChoices):
        BANK = "bank", "Banka"
        CASH = "cash", "Nakit"

    name = models.CharField(max_length=50)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.BANK)
    opening_balance = models.DecimalField(**MONEY, default=Decimal("0"))  # negative allowed (overdraft)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaymentPlan(OwnedModel):
    """
    Repeating money movement: recurring (subscription, rent, salary) or installment purchase.
    Each occurrence becomes a Transaction, either automatically on the due date (auto_pay)
    or when the user marks it as paid.
    """

    class PlanType(models.TextChoices):
        RECURRING = "recurring", "Düzenli"
        INSTALLMENT = "installment", "Taksitli"

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Haftalık"
        MONTHLY = "monthly", "Aylık"
        YEARLY = "yearly", "Yıllık"

    plan_type = models.CharField(max_length=12, choices=PlanType.choices)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.EXPENSE)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(**MONEY, validators=[POSITIVE])  # per occurrence (installment: base share)
    total_amount = models.DecimalField(**MONEY, validators=[POSITIVE], null=True, blank=True)  # installment only
    installment_count = models.PositiveSmallIntegerField(null=True, blank=True)  # installment only
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
    interval = models.PositiveSmallIntegerField(default=1)  # every N periods
    start_date = models.DateField()
    next_due_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # recurring only
    paid_count = models.PositiveSmallIntegerField(default=0)
    auto_pay = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["next_due_date"]
        indexes = [
            models.Index(fields=["user", "is_active", "next_due_date"]),
            models.Index(fields=["auto_pay", "is_active", "next_due_date"]),
        ]

    def __str__(self):
        return self.description


class Transaction(OwnedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manuel"
        STATEMENT = "statement", "Ekstre"
        PLAN = "plan", "Ödeme Planı"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(**MONEY, validators=[POSITIVE])
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    plan = models.ForeignKey(
        PaymentPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    plan_sequence = models.PositiveSmallIntegerField(null=True, blank=True)  # n-th occurrence of the plan

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "-date"]),
            models.Index(fields=["account", "kind"]),
        ]

    def __str__(self):
        return f"{self.date} {self.kind} {self.amount}"
