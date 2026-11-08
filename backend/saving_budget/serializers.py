from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from core.serializers import OwnedPrimaryKeyRelatedField

from .models import Account, Category, GoalContribution, Kind, RecurringPayment, SavingGoal, Transaction


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
    class Meta:
        model = Account
        fields = ["id", "name", "account_type", "bank", "last4", "is_archived", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_last4(self, value):
        if value and (len(value) != 4 or not value.isdigit()):
            raise serializers.ValidationError("Son 4 hane yalnızca 4 rakam olmalı.")
        return value


def _check_category_kind(category, kind):
    if category and kind and category.kind != kind:
        raise serializers.ValidationError({"category": "Kategori türü işlem türüyle uyuşmuyor."})


class TransactionSerializer(serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    account = OwnedPrimaryKeyRelatedField(queryset=Account.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Transaction
        fields = [
            "id", "kind", "amount", "date", "description", "note",
            "category", "account", "source", "recurring_payment", "created_at",
        ]
        read_only_fields = ["id", "source", "recurring_payment", "created_at"]

    def validate(self, attrs):
        _check_category_kind(
            attrs.get("category", getattr(self.instance, "category", None)),
            attrs.get("kind", getattr(self.instance, "kind", None)),
        )
        return attrs


class RecurringPaymentSerializer(serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    account = OwnedPrimaryKeyRelatedField(queryset=Account.objects.all(), allow_null=True, required=False)
    next_due_date = serializers.DateField(required=False)
    is_overdue = serializers.SerializerMethodField()
    remaining_installments = serializers.SerializerMethodField()

    class Meta:
        model = RecurringPayment
        fields = [
            "id", "name", "amount", "category", "account", "frequency", "interval",
            "start_date", "next_due_date", "end_date", "installment_count", "paid_count",
            "remaining_installments", "is_active", "is_overdue", "note", "created_at",
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
        _check_category_kind(attrs.get("category"), Kind.EXPENSE)
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "Bitiş tarihi başlangıçtan önce olamaz."})
        if self.instance is None and "next_due_date" not in attrs:
            attrs["next_due_date"] = start
        return attrs


class PayRecurringSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    date = serializers.DateField(required=False)


class SavingGoalSerializer(serializers.ModelSerializer):
    current_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = SavingGoal
        fields = [
            "id", "name", "target_amount", "target_date", "status", "note",
            "current_amount", "progress_percent", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_progress_percent(self, obj):
        current = getattr(obj, "current_amount", None) or Decimal("0")
        return float(min(current / obj.target_amount * 100, Decimal("100")).quantize(Decimal("0.1")))


class GoalContributionSerializer(serializers.ModelSerializer):
    goal = OwnedPrimaryKeyRelatedField(queryset=SavingGoal.objects.all())

    class Meta:
        model = GoalContribution
        fields = ["id", "goal", "amount", "date", "note", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_amount(self, value):
        if value == 0:
            raise serializers.ValidationError("Tutar sıfır olamaz.")
        return value
