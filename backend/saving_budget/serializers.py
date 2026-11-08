from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from core.serializers import OwnedPrimaryKeyRelatedField

from .models import Account, Category, Kind, PaymentPlan, Transaction
from .services import create_plan


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


def _check_category_kind(category, kind):
    if category and kind and category.kind != kind:
        raise serializers.ValidationError({"category": "Kategori türü işlem türüyle uyuşmuyor."})


class TransactionSerializer(serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    account = OwnedPrimaryKeyRelatedField(queryset=Account.objects.all())
    plan_info = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id", "kind", "amount", "date", "description", "note", "category", "account",
            "source", "plan", "plan_sequence", "plan_info", "created_at",
        ]
        read_only_fields = ["id", "source", "plan", "plan_sequence", "created_at"]

    def get_plan_info(self, obj):
        """e.g. {"plan_type": "installment", "label": "2/6"} for list display."""
        plan = obj.plan
        if plan is None:
            return None
        if plan.plan_type == PaymentPlan.PlanType.INSTALLMENT:
            label = f"{obj.plan_sequence}/{plan.installment_count}"
        else:
            label = plan.get_frequency_display()
        return {"plan_type": plan.plan_type, "label": label}

    def validate(self, attrs):
        _check_category_kind(_current(self, attrs, "category"), _current(self, attrs, "kind"))
        return attrs


class PaymentPlanSerializer(serializers.ModelSerializer):
    """Create = one entry point for repeating expenses/incomes. Fields fixed after creation are read-only on update."""

    IMMUTABLE = ("plan_type", "kind", "total_amount", "installment_count", "start_date")

    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    account = OwnedPrimaryKeyRelatedField(queryset=Account.objects.all())
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    next_due_date = serializers.DateField(required=False)
    is_overdue = serializers.SerializerMethodField()
    remaining_installments = serializers.SerializerMethodField()

    class Meta:
        model = PaymentPlan
        fields = [
            "id", "plan_type", "kind", "description", "amount", "total_amount", "installment_count",
            "category", "account", "frequency", "interval", "start_date", "next_due_date", "end_date",
            "paid_count", "remaining_installments", "auto_pay", "is_active", "is_overdue", "note", "created_at",
        ]
        read_only_fields = ["id", "paid_count", "created_at"]

    def get_is_overdue(self, obj):
        return obj.is_active and obj.next_due_date < timezone.localdate()

    def get_remaining_installments(self, obj):
        if obj.installment_count is None:
            return None
        return max(obj.installment_count - obj.paid_count, 0)

    def validate_interval(self, value):
        if value < 1:
            raise serializers.ValidationError("Tekrar aralığı en az 1 olmalı.")
        return value

    def validate(self, attrs):
        if self.instance:
            return self._validate_update(attrs)

        plan_type = attrs.get("plan_type")
        attrs.pop("next_due_date", None)  # always starts at start_date
        if plan_type == PaymentPlan.PlanType.INSTALLMENT:
            if attrs.get("kind", Kind.EXPENSE) != Kind.EXPENSE:
                raise serializers.ValidationError({"kind": "Taksit yalnızca gider için kullanılabilir."})
            if not attrs.get("total_amount"):
                raise serializers.ValidationError({"total_amount": "Taksitli işlemde toplam tutar gerekli."})
            if (attrs.get("installment_count") or 0) < 2:
                raise serializers.ValidationError({"installment_count": "Taksit sayısı en az 2 olmalı."})
            attrs.pop("amount", None)
        else:
            if not attrs.get("amount"):
                raise serializers.ValidationError({"amount": "Tutar gerekli."})
            attrs["total_amount"] = attrs["installment_count"] = None
            start, end = attrs.get("start_date"), attrs.get("end_date")
            if start and end and end < start:
                raise serializers.ValidationError({"end_date": "Bitiş tarihi başlangıçtan önce olamaz."})

        _check_category_kind(attrs.get("category"), attrs.get("kind", Kind.EXPENSE))
        return attrs

    def _validate_update(self, attrs):
        for name in self.IMMUTABLE:
            if name in attrs and attrs[name] != getattr(self.instance, name):
                raise serializers.ValidationError({name: "Bu alan plan oluşturulduktan sonra değiştirilemez."})
        if self.instance.plan_type == PaymentPlan.PlanType.INSTALLMENT:
            for name in ("amount", "end_date", "frequency", "interval"):
                attrs.pop(name, None)
        _check_category_kind(_current(self, attrs, "category"), self.instance.kind)
        return attrs

    def create(self, validated_data):
        return create_plan(**validated_data)


def _money():
    return serializers.DecimalField(max_digits=14, decimal_places=2)


class SummaryAccountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    account_type = serializers.CharField()
    balance = _money()


class MonthlySummarySerializer(serializers.Serializer):
    """Output-only: keeps money as strings like every other endpoint."""

    month = serializers.CharField()
    income = _money()
    expense = _money()
    net = _money()
    accounts = SummaryAccountSerializer(many=True)
    total_balance = _money()
    planned_income = _money()
    planned_expense = _money()
    projected_balance = _money()


class PayPlanSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    date = serializers.DateField(required=False)
