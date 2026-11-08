from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from core.serializers import OwnedPrimaryKeyRelatedField

from .models import Account, Category, Kind, Series, Transaction
from .services import create_entry


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "kind", "icon", "color", "is_archived", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        user = self.context["request"].user
        name = attrs.get("name", getattr(self.instance, "name", None))
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        qs = Category.objects.filter(user=user, kind=kind, name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"name": "Bu isimde bir kategori zaten var."})
        return attrs


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Account
        fields = ["id", "name", "account_type", "opening_balance", "balance", "is_archived", "created_at"]
        read_only_fields = ["id", "created_at"]


def _current(serializer, attrs, name):
    return attrs.get(name, getattr(serializer.instance, name, None))


class TransactionSerializer(serializers.ModelSerializer):
    """Read + update. Status changes go through the pay/unpay actions."""

    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    account = OwnedPrimaryKeyRelatedField(queryset=Account.objects.all())
    is_overdue = serializers.SerializerMethodField()
    series_info = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id", "kind", "amount", "date", "status", "paid_on", "auto_pay", "is_overdue",
            "description", "note", "category", "account", "source", "series", "sequence",
            "series_info", "created_at",
        ]
        read_only_fields = ["id", "status", "paid_on", "source", "series", "sequence", "created_at"]

    def get_is_overdue(self, obj):
        return obj.status == Transaction.Status.PENDING and obj.date < timezone.localdate()

    def get_series_info(self, obj):
        """e.g. {"series_type": "installment", "label": "2/6", "is_active": true}"""
        s = obj.series
        if s is None:
            return None
        if s.series_type == Series.SeriesType.INSTALLMENT:
            label = f"{obj.sequence}/{s.installment_count}"
        else:
            label = s.get_frequency_display()
        return {"series_type": s.series_type, "label": label, "is_active": s.is_active}

    def validate(self, attrs):
        if self.instance and self.instance.series_id and attrs.get("kind", self.instance.kind) != self.instance.kind:
            raise serializers.ValidationError({"kind": "Tekrarlayan bir kaydın türü değiştirilemez."})
        category, kind = _current(self, attrs, "category"), _current(self, attrs, "kind")
        if category and kind and category.kind != kind:
            raise serializers.ValidationError({"category": "Kategori türü işlem türüyle uyuşmuyor."})
        return attrs


class TransactionCreateSerializer(TransactionSerializer):
    """
    Create = single entry form. repeat: none | recurring | installment.
    For installment, `amount` is the TOTAL amount; the backend splits it.
    """

    repeat = serializers.ChoiceField(choices=["none", "recurring", "installment"], default="none", write_only=True)
    frequency = serializers.ChoiceField(choices=Series.Frequency.choices, default=Series.Frequency.MONTHLY, write_only=True)
    interval = serializers.IntegerField(min_value=1, default=1, write_only=True)
    end_date = serializers.DateField(required=False, allow_null=True, write_only=True)
    installment_count = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + ["repeat", "frequency", "interval", "end_date", "installment_count"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        repeat = attrs["repeat"]
        if repeat == "installment":
            if attrs["kind"] != Kind.EXPENSE:
                raise serializers.ValidationError({"kind": "Taksit yalnızca gider için kullanılabilir."})
            if (attrs.get("installment_count") or 0) < 2:
                raise serializers.ValidationError({"installment_count": "Taksit sayısı en az 2 olmalı."})
        if repeat == "recurring" and attrs.get("end_date") and attrs["end_date"] < attrs["date"]:
            raise serializers.ValidationError({"end_date": "Bitiş tarihi başlangıçtan önce olamaz."})
        if repeat != "none" and not attrs.get("description"):
            raise serializers.ValidationError({"description": "Tekrarlayan kayıtlar için açıklama gerekli."})
        return attrs

    def create(self, validated_data):
        options = {k: validated_data.pop(k, None) for k in ("frequency", "interval", "end_date", "installment_count")}
        repeat = validated_data.pop("repeat")
        user = validated_data.pop("user")
        return create_entry(user=user, repeat=repeat, data=validated_data, series_options=options)


class PaySerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    date = serializers.DateField(required=False)


def _money():
    return serializers.DecimalField(max_digits=14, decimal_places=2)


class SummaryAccountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    account_type = serializers.CharField()
    balance = _money()


class MonthlySummarySerializer(serializers.Serializer):
    """Output-only: money as strings like every other endpoint."""

    month = serializers.CharField()
    income = _money()
    income_paid = _money()
    income_pending = _money()
    expense = _money()
    expense_paid = _money()
    expense_pending = _money()
    net = _money()
    accounts = SummaryAccountSerializer(many=True)
    current_balance = _money()
    overdue_income = _money()
    overdue_expense = _money()
    projected_balance = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
