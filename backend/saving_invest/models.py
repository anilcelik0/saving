from django.conf import settings
from django.db import models

from core.base_models import BaseModel

MONEY = {"max_digits": 20, "decimal_places": 2}
LINKED_ENTRY = {"on_delete": models.SET_NULL, "null": True, "blank": True, "related_name": "+"}


class Asset(BaseModel):
    """Tradable asset (shared catalog for all users). Rows are synced from `catalog.ASSETS`."""

    class Type(models.TextChoices):
        CURRENCY = "currency", "Döviz"
        GOLD = "gold", "Altın"
        SILVER = "silver", "Gümüş"

    code = models.CharField(max_length=20, unique=True)  # e.g. "USD", "GOLD_GRAM"
    name = models.CharField(max_length=50)
    asset_type = models.CharField(max_length=10, choices=Type.choices)
    unit = models.CharField(max_length=10)  # display unit: "USD", "gram", "adet"
    quantity_decimals = models.PositiveSmallIntegerField(default=2)
    provider = models.CharField(max_length=30)  # key in providers.PROVIDERS
    source_code = models.CharField(max_length=20)  # symbol at the provider
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return self.name


class AssetPrice(BaseModel):
    """Daily price row (one per asset and day). buy = price the market pays you, sell = price you pay."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    buy = models.DecimalField(max_digits=20, decimal_places=4)
    sell = models.DecimalField(max_digits=20, decimal_places=4)
    source_time = models.DateTimeField(null=True, blank=True)  # provider's own update time, if given

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["asset", "date"], name="uniq_asset_price_per_day")]

    def __str__(self):
        return f"{self.asset.code} {self.date}: {self.buy}/{self.sell}"


class Trade(BaseModel):
    """
    A purchase, or a reduction of a holding (no sale/profit tracking). Optionally mirrored in the budget:
    a purchase as an expense of `account`, a reduction's `proceeds` as income to `account`.
    """

    class Side(models.TextChoices):
        BUY = "buy", "Alış"
        REDUCE = "reduce", "Azaltma"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="trades")
    side = models.CharField(max_length=6, choices=Side.choices)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    unit_price = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)  # TRY, purchases only
    proceeds = models.DecimalField(**MONEY, null=True, blank=True)  # TRY received on a reduction (optional)
    date = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    account = models.ForeignKey("saving_budget.Account", **LINKED_ENTRY)
    budget_entry = models.OneToOneField("saving_budget.Transaction", **LINKED_ENTRY)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "asset", "date"])]

    def __str__(self):
        return f"{self.side} {self.quantity} {self.asset.code}"


class Deposit(BaseModel):
    """
    Time deposit (vadeli mevduat). The user sets rate, maturity date and maturity amount. At maturity it is either
    renewed (new deposit; principal = maturity amount) or closed (maturity amount optionally added to an account).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Aktif"
        RENEWED = "renewed", "Yenilendi"
        CLOSED = "closed", "Kapandı"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=60)  # e.g. "Enpara 32 gün"
    principal = models.DecimalField(**MONEY)
    annual_rate = models.DecimalField(max_digits=7, decimal_places=4)  # percent, e.g. 42.5
    start_date = models.DateField()
    maturity_date = models.DateField()
    maturity_amount = models.DecimalField(**MONEY)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    note = models.CharField(max_length=200, blank=True)
    previous = models.OneToOneField("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="renewal")
    # budget mirrors: opening = expense of `account`, closing = income to `close_account`
    account = models.ForeignKey("saving_budget.Account", **LINKED_ENTRY)
    open_entry = models.OneToOneField("saving_budget.Transaction", **LINKED_ENTRY)
    closed_on = models.DateField(null=True, blank=True)
    close_amount = models.DecimalField(**MONEY, null=True, blank=True)
    close_account = models.ForeignKey("saving_budget.Account", **LINKED_ENTRY)
    close_entry = models.OneToOneField("saving_budget.Transaction", **LINKED_ENTRY)

    class Meta:
        ordering = ["maturity_date", "created_at"]
        indexes = [models.Index(fields=["user", "status"])]

    def __str__(self):
        return f"{self.name} {self.principal} → {self.maturity_amount} ({self.maturity_date})"
