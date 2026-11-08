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
    class AccountType(models.TextChoices):
        BANK = "bank", "Banka Hesabı"
        CREDIT_CARD = "credit_card", "Kredi Kartı"
        CASH = "cash", "Nakit"

    class Bank(models.TextChoices):
        ZIRAAT = "ziraat", "Ziraat Bankası"
        ISBANK = "isbank", "İş Bankası"
        GARANTI = "garanti", "Garanti BBVA"
        YAPIKREDI = "yapikredi", "Yapı Kredi"
        AKBANK = "akbank", "Akbank"
        HALKBANK = "halkbank", "Halkbank"
        VAKIFBANK = "vakifbank", "VakıfBank"
        QNB = "qnb", "QNB"
        ENPARA = "enpara", "Enpara"
        DENIZBANK = "denizbank", "DenizBank"
        TEB = "teb", "TEB"
        ING = "ing", "ING"
        KUVEYTTURK = "kuveytturk", "Kuveyt Türk"
        OTHER = "other", "Diğer"

    name = models.CharField(max_length=50)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    bank = models.CharField(max_length=20, choices=Bank.choices, blank=True)
    last4 = models.CharField(max_length=4, blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class RecurringPayment(OwnedModel):
    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Haftalık"
        MONTHLY = "monthly", "Aylık"
        YEARLY = "yearly", "Yıllık"

    name = models.CharField(max_length=100)
    amount = models.DecimalField(**MONEY, validators=[POSITIVE])
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
    interval = models.PositiveSmallIntegerField(default=1)  # every N periods
    start_date = models.DateField()
    next_due_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    installment_count = models.PositiveSmallIntegerField(null=True, blank=True)  # taksit
    paid_count = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["next_due_date"]
        indexes = [models.Index(fields=["user", "is_active", "next_due_date"])]

    def __str__(self):
        return self.name


class Transaction(OwnedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manuel"
        STATEMENT = "statement", "Ekstre"
        RECURRING = "recurring", "Düzenli Ödeme"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(**MONEY, validators=[POSITIVE])
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    recurring_payment = models.ForeignKey(
        RecurringPayment, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "-date"])]

    def __str__(self):
        return f"{self.date} {self.kind} {self.amount}"


class SavingGoal(OwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Aktif"
        COMPLETED = "completed", "Tamamlandı"
        CANCELLED = "cancelled", "İptal"

    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(**MONEY, validators=[POSITIVE])
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["status", "target_date", "name"]

    def __str__(self):
        return self.name


class GoalContribution(BaseModel):
    """Positive amount = deposit into goal, negative = withdrawal."""

    goal = models.ForeignKey(SavingGoal, on_delete=models.CASCADE, related_name="contributions")
    amount = models.DecimalField(**MONEY)
    date = models.DateField()
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
