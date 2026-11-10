from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from core.serializers import OwnedPrimaryKeyRelatedField
from saving_budget.models import Account

from .models import Asset, AssetPrice, Deposit, Trade
from .services import (
    change_pct, default_maturity_amount, deposit_value, find_overdraw, holding_quantity, qty_text, sync_deposit_open,
    sync_trade_entry,
)


def _not_future(value):
    if value > timezone.localdate():
        raise serializers.ValidationError("İleri tarih girilemez.")
    return value


def _positive(value):
    if value is not None and value <= 0:
        raise serializers.ValidationError("Değer sıfırdan büyük olmalı.")
    return value


def _account_field():
    return OwnedPrimaryKeyRelatedField(queryset=Account.objects.filter(is_archived=False), required=False,
                                       allow_null=True)


class AssetPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetPrice
        fields = ["date", "buy", "sell", "source_time"]


class AssetSerializer(serializers.ModelSerializer):
    """Catalog row + latest price; `prices` context = {asset_id: (latest, previous)} from services.latest_prices."""

    price = serializers.SerializerMethodField()
    change_pct = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = ["id", "code", "name", "asset_type", "unit", "quantity_decimals", "price", "change_pct"]

    def _prices(self, obj):
        return self.context.get("prices", {}).get(obj.pk, (None, None))

    def get_price(self, obj):
        latest = self._prices(obj)[0]
        return AssetPriceSerializer(latest).data if latest else None

    def get_change_pct(self, obj):
        value = change_pct(*self._prices(obj))
        return str(value) if value is not None else None


class AssetBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ["code", "name", "asset_type", "unit", "quantity_decimals"]


class TradeSerializer(serializers.ModelSerializer):
    """
    `asset` = asset code (e.g. "GOLD_GRAM").
    buy: quantity + unit_price; with `account` the total is written to the budget as an expense of that account.
    reduce: quantity only; optional `proceeds` (TRY) + `account` -> income to that account. Never below zero held.
    """

    asset = serializers.SlugRelatedField(slug_field="code", queryset=Asset.objects.filter(is_active=True))
    asset_info = AssetBriefSerializer(source="asset", read_only=True)
    account = _account_field()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = ["id", "asset", "asset_info", "side", "quantity", "unit_price", "proceeds", "total", "date", "note",
                  "account", "budget_entry", "created_at"]
        read_only_fields = ["budget_entry", "created_at"]
        extra_kwargs = {"unit_price": {"required": False}, "proceeds": {"required": False}}

    def get_total(self, obj):
        if obj.side == Trade.Side.BUY:
            return str((obj.quantity * obj.unit_price).quantize(Decimal("0.01")))
        return str(obj.proceeds) if obj.proceeds is not None else None

    validate_quantity = staticmethod(_positive)
    validate_unit_price = staticmethod(_positive)
    validate_proceeds = staticmethod(_positive)
    validate_date = staticmethod(_not_future)

    def validate(self, attrs):
        instance = self.instance
        value = lambda name: attrs.get(name, getattr(instance, name, None))  # noqa: E731
        asset, side, quantity, trade_date = value("asset"), value("side"), value("quantity"), value("date")

        if side == Trade.Side.BUY:
            if not value("unit_price"):
                raise serializers.ValidationError({"unit_price": "Alış için birim fiyat girin."})
            attrs["proceeds"] = None
        else:
            attrs["unit_price"] = None
            if value("proceeds") and not value("account"):
                raise serializers.ValidationError({"account": "TL tutarın ekleneceği hesabı seçin."})
            if value("account") and not value("proceeds"):
                raise serializers.ValidationError({"proceeds": "Hesaba eklenecek TL tutarını girin."})

        if -quantity.normalize().as_tuple().exponent > asset.quantity_decimals:
            raise serializers.ValidationError(
                {"quantity": f"{asset.name} için en fazla {asset.quantity_decimals} ondalık basamak girilebilir."})

        user = self.context["request"].user
        same_asset = instance is not None and instance.asset_id == asset.pk
        if instance is not None and not same_asset and find_overdraw(user, instance.asset, exclude=instance):
            raise serializers.ValidationError({"asset": "Bu işlem çıkarılırsa eski varlıkta eldeki miktar eksiye düşer."})
        if overdrawn_on := find_overdraw(user, asset, exclude=instance if same_asset else None,
                                         new=(trade_date, side, quantity)):
            held = holding_quantity(user, asset)
            raise serializers.ValidationError({"quantity": (
                f"{overdrawn_on:%d.%m.%Y} tarihinde eldeki miktar eksiye düşüyor "
                f"(şu an elinizde {qty_text(held)} {asset.unit} var).")})
        return attrs

    def create(self, validated_data):
        trade = super().create(validated_data)
        sync_trade_entry(trade)
        return trade

    def update(self, instance, validated_data):
        trade = super().update(instance, validated_data)
        sync_trade_entry(trade)
        return trade


class DepositSerializer(serializers.ModelSerializer):
    """
    Time deposit. `maturity_amount` may be omitted: gross simple interest from the rate is used (user can edit).
    With `account`, the principal is written to the budget as an expense of that account on the start date.
    """

    account = _account_field()
    is_matured = serializers.SerializerMethodField()
    term_days = serializers.SerializerMethodField()
    days_left = serializers.SerializerMethodField()
    interest = serializers.SerializerMethodField()
    current_value = serializers.SerializerMethodField()

    class Meta:
        model = Deposit
        fields = ["id", "name", "principal", "annual_rate", "start_date", "maturity_date", "maturity_amount",
                  "interest", "term_days", "days_left", "is_matured", "current_value", "status", "note", "account",
                  "previous", "closed_on", "close_amount", "close_account", "created_at"]
        read_only_fields = ["status", "previous", "closed_on", "close_amount", "close_account", "created_at"]
        extra_kwargs = {"maturity_amount": {"required": False}}

    def get_is_matured(self, obj):
        return obj.status == Deposit.Status.ACTIVE and obj.maturity_date <= timezone.localdate()

    def get_term_days(self, obj):
        return (obj.maturity_date - obj.start_date).days

    def get_days_left(self, obj):
        return max((obj.maturity_date - timezone.localdate()).days, 0)

    def get_interest(self, obj):
        return str(obj.maturity_amount - obj.principal)

    def get_current_value(self, obj):
        return str(deposit_value(obj)) if obj.status == Deposit.Status.ACTIVE else None

    validate_principal = staticmethod(_positive)
    validate_annual_rate = staticmethod(_positive)
    validate_start_date = staticmethod(_not_future)

    def validate(self, attrs):
        instance = self.instance
        if instance is not None and instance.status != Deposit.Status.ACTIVE:
            raise serializers.ValidationError({"detail": "Yalnızca aktif mevduat düzenlenebilir."})
        value = lambda name: attrs.get(name, getattr(instance, name, None))  # noqa: E731
        principal, start, end = value("principal"), value("start_date"), value("maturity_date")
        if end <= start:
            raise serializers.ValidationError({"maturity_date": "Vade sonu başlangıç tarihinden sonra olmalı."})
        rate_changed = any(k in attrs for k in ("principal", "annual_rate", "start_date", "maturity_date"))
        if not attrs.get("maturity_amount") and (instance is None or rate_changed):
            attrs["maturity_amount"] = default_maturity_amount(principal, value("annual_rate"), start, end)
        if value("maturity_amount") < principal:
            raise serializers.ValidationError({"maturity_amount": "Vade sonu tutarı anaparadan küçük olamaz."})
        return attrs

    def create(self, validated_data):
        deposit = super().create(validated_data)
        sync_deposit_open(deposit)
        return deposit

    def update(self, instance, validated_data):
        deposit = super().update(instance, validated_data)
        sync_deposit_open(deposit)
        return deposit


class DepositCloseSerializer(serializers.Serializer):
    account = _account_field()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False, validators=[_positive])
    date = serializers.DateField(required=False, validators=[_not_future])


class DepositRenewSerializer(serializers.Serializer):
    annual_rate = serializers.DecimalField(max_digits=7, decimal_places=4, validators=[_positive])
    maturity_date = serializers.DateField()
    maturity_amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    name = serializers.CharField(max_length=60, required=False)

    def validate(self, attrs):
        deposit = self.context["deposit"]
        if attrs["maturity_date"] <= deposit.maturity_date:
            raise serializers.ValidationError({"maturity_date": "Yeni vade sonu eski vade sonundan sonra olmalı."})
        if attrs.get("maturity_amount") is not None and attrs["maturity_amount"] < deposit.maturity_amount:
            raise serializers.ValidationError({"maturity_amount": "Vade sonu tutarı anaparadan küçük olamaz."})
        return attrs


class PositionSerializer(serializers.Serializer):
    asset = AssetBriefSerializer()
    quantity = serializers.DecimalField(max_digits=20, decimal_places=6)
    average_cost = serializers.DecimalField(max_digits=20, decimal_places=4)
    cost = serializers.DecimalField(max_digits=20, decimal_places=2)
    price = serializers.DecimalField(max_digits=20, decimal_places=4, allow_null=True)
    price_date = serializers.DateField(allow_null=True)
    change_pct = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    value = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)
    gain = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)
    gain_pct = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)


class PortfolioTotalsSerializer(serializers.Serializer):
    assets_cost = serializers.DecimalField(max_digits=20, decimal_places=2)
    assets_value = serializers.DecimalField(max_digits=20, decimal_places=2)
    assets_gain = serializers.DecimalField(max_digits=20, decimal_places=2)
    assets_gain_pct = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    deposits_principal = serializers.DecimalField(max_digits=20, decimal_places=2)
    deposits_value = serializers.DecimalField(max_digits=20, decimal_places=2)
    deposits_at_maturity = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_value = serializers.DecimalField(max_digits=20, decimal_places=2)


class PortfolioSerializer(serializers.Serializer):
    items = PositionSerializer(many=True)
    totals = PortfolioTotalsSerializer()
