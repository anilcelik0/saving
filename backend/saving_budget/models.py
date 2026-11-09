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
        CANCELLED = "cancelled", "İptal edildi"  # refunded / skipped: kept for history, ignored in totals

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
    external_key = models.CharField(max_length=80, blank=True, db_index=True)  # statement dedupe key

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


def statement_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"statements/{instance.user_id}/{instance.id}.{ext}"


def private_storage():
    from django.core.files.storage import storages

    return storages["private"]


class StatementImport(OwnedModel):
    """
    An uploaded bank statement. Parsed asynchronously into StatementLines (preview),
    reviewed by the user, then confirmed into Transactions. The file is deleted after parsing.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Sırada"
        PARSING = "parsing", "Okunuyor"
        READY = "ready", "Önizleme hazır"
        FAILED = "failed", "Hata"
        IMPORTED = "imported", "Aktarıldı"

    class StatementType(models.TextChoices):
        ACCOUNT = "account", "Hesap ekstresi"
        CARD = "card", "Kredi kartı ekstresi"

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="statements")
    file = models.FileField(upload_to=statement_upload_path, storage=private_storage, blank=True)
    original_name = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=255, blank=True)
    bank = models.CharField(max_length=30, blank=True)  # bank slug, e.g. "vakifbank"
    is_generic = models.BooleanField(default=False)  # read by the fallback parser -> user should double-check
    statement_type = models.CharField(max_length=10, choices=StatementType.choices, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    closing_balance = models.DecimalField(**MONEY, null=True, blank=True)  # account statements
    imported_count = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    cancelled_count = models.PositiveIntegerField(default=0)  # purchases cancelled by refunds

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name


class StatementLine(BaseModel):
    class Action(models.TextChoices):
        IMPORT = "import", "Yeni kayıt olarak aktar"
        MATCH = "match", "Bekleyen kayıtla eşleştir"
        REFUND = "refund", "İlgili harcamayı iptal et (iade)"
        SKIP = "skip", "Aktarma"

    class SkipReason(models.TextChoices):
        NONE = "", "-"
        DUPLICATE = "duplicate", "Daha önce aktarılmış"
        CARD_PAYMENT = "card_payment", "Kredi kartı borç ödemesi"
        TRANSFER = "transfer", "Kendi hesabına virman"
        INVESTMENT = "investment", "Yatırım / mevduat hareketi"
        USER = "user", "Kullanıcı seçimi"

    statement = models.ForeignKey(StatementImport, on_delete=models.CASCADE, related_name="lines")
    line_no = models.PositiveIntegerField()
    date = models.DateField()
    description = models.CharField(max_length=255)
    raw_text = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(**MONEY, validators=[POSITIVE])
    installment = models.CharField(max_length=30, blank=True)  # e.g. "1/3", "kalan 2"
    external_key = models.CharField(max_length=80)
    action = models.CharField(max_length=10, choices=Action.choices, default=Action.IMPORT)
    skip_reason = models.CharField(max_length=15, choices=SkipReason.choices, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    matched_transaction = models.ForeignKey(
        Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )  # action=match: pending candidate; action=refund: existing paid purchase to cancel
    refund_target_line = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )  # action=refund: purchase line in the same statement to cancel
    result_transaction = models.ForeignKey(
        Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )  # created/updated/cancelled on confirm

    class Meta:
        ordering = ["line_no"]


class MerchantCategoryRule(OwnedModel):
    """Learned from the user's category choices: merchant key -> category (applied before built-in rules)."""

    kind = models.CharField(max_length=10, choices=Kind.choices)
    merchant_key = models.CharField(max_length=60)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="merchant_rules")
    hits = models.PositiveIntegerField(default=0)  # times applied to statement lines

    class Meta:
        ordering = ["merchant_key"]
        constraints = [
            models.UniqueConstraint(fields=["user", "kind", "merchant_key"], name="uniq_merchant_rule_per_user_kind"),
        ]

    def __str__(self):
        return f"{self.merchant_key} -> {self.category}"
