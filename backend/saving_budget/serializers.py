from decimal import Decimal

from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers

from core.serializers import OwnedPrimaryKeyRelatedField

from .models import (
    Account, Category, Kind, MerchantCategoryRule, Series, StatementImport, StatementLine, Transaction,
)
from .services import create_entry
from .statement_services import apply_learned_category
from .statements.registry import BANK_LABELS


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
        fields = ["id", "name", "account_type", "opening_balance", "statement_day", "card_name", "balance",
                  "is_archived", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_statement_day(self, value):
        if value is not None and not 1 <= value <= 31:
            raise serializers.ValidationError("Kesim günü 1 ile 31 arasında olmalı.")
        return value


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
            "id", "kind", "amount", "date", "status", "paid_on", "auto_pay", "is_card", "in_balance", "is_overdue",
            "description", "note", "category", "account", "source", "series", "sequence",
            "series_info", "created_at",
        ]
        read_only_fields = ["id", "status", "paid_on", "in_balance", "source", "series", "sequence", "created_at"]

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
            raise serializers.ValidationError({"description": "Tekrarlayan kayıtlar için isim gerekli."})
        return attrs

    def create(self, validated_data):
        options = {k: validated_data.pop(k, None) for k in ("frequency", "interval", "end_date", "installment_count")}
        repeat = validated_data.pop("repeat")
        user = validated_data.pop("user")
        return create_entry(user=user, repeat=repeat, data=validated_data, series_options=options)


class StatementImportSerializer(serializers.ModelSerializer):
    account = OwnedPrimaryKeyRelatedField(queryset=Account.objects.all())
    file = serializers.FileField(write_only=True)
    counts = serializers.SerializerMethodField()
    bank_label = serializers.SerializerMethodField()

    class Meta:
        model = StatementImport
        fields = [
            "id", "account", "file", "exclude_from_balance", "original_name", "status", "error", "bank",
            "bank_label", "is_generic", "statement_type", "period_start", "period_end", "closing_balance",
            "imported_count", "matched_count", "cancelled_count", "counts", "check_status", "check_message",
            "created_at",
        ]
        read_only_fields = [
            "id", "original_name", "status", "error", "bank", "is_generic", "statement_type", "period_start",
            "period_end", "closing_balance", "imported_count", "matched_count", "cancelled_count", "check_status",
            "check_message", "created_at",
        ]

    def get_bank_label(self, obj):
        return BANK_LABELS.get(obj.bank, obj.bank)

    def get_counts(self, obj):
        """Lines per action, e.g. {"import": 18, "match": 1, "skip": 4}."""
        counts = {action: 0 for action in StatementLine.Action.values}
        for row in obj.lines.values("action").annotate(n=Count("id")):
            counts[row["action"]] = row["n"]
        return counts

    def validate_file(self, file):
        ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
        if ext not in ("pdf", "xlsx"):
            raise serializers.ValidationError("Yalnızca PDF veya Excel (.xlsx) ekstre yüklenebilir.")
        if file.size > settings.STATEMENT_MAX_UPLOAD_MB * 1024 * 1024:
            raise serializers.ValidationError(f"Dosya en fazla {settings.STATEMENT_MAX_UPLOAD_MB} MB olabilir.")
        return file

    def create(self, validated_data):
        validated_data["original_name"] = validated_data["file"].name[:255]
        return super().create(validated_data)


class StatementLineSerializer(serializers.ModelSerializer):
    category = OwnedPrimaryKeyRelatedField(queryset=Category.objects.all(), allow_null=True, required=False)
    matched_transaction = OwnedPrimaryKeyRelatedField(
        queryset=Transaction.objects.filter(status=Transaction.Status.PENDING), allow_null=True, required=False
    )
    matched_info = serializers.SerializerMethodField()
    refund_info = serializers.SerializerMethodField()

    class Meta:
        model = StatementLine
        fields = [
            "id", "line_no", "date", "description", "kind", "amount", "installment", "action", "skip_reason",
            "category", "matched_transaction", "matched_info", "refund_target_line", "refund_info",
            "result_transaction",
        ]
        read_only_fields = [
            "id", "line_no", "date", "description", "kind", "amount", "installment", "skip_reason",
            "refund_target_line", "result_transaction",
        ]

    def get_matched_info(self, obj):
        t = obj.matched_transaction
        if t is None or obj.action == StatementLine.Action.REFUND:
            return None
        return {"description": t.description, "date": t.date, "amount": t.amount}

    def get_refund_info(self, obj):
        """The purchase this refund will cancel (a line in this statement or an existing transaction)."""
        target = obj.refund_target_line or (obj.matched_transaction if obj.action == StatementLine.Action.REFUND else None)
        if target is None:
            return None
        return {"description": target.description, "date": target.date, "amount": target.amount,
                "in_statement": obj.refund_target_line_id is not None}

    def validate(self, attrs):
        line = self.instance
        if line.statement.status != StatementImport.Status.READY:
            raise serializers.ValidationError({"detail": "Aktarılmış ekstre satırları değiştirilemez."})
        action = attrs.get("action", line.action)
        if action != StatementLine.Action.SKIP and line.skip_reason == StatementLine.SkipReason.DUPLICATE:
            raise serializers.ValidationError({"action": "Bu satır daha önce aktarılmış."})
        match = attrs.get("matched_transaction", line.matched_transaction)
        if action == StatementLine.Action.REFUND and not (line.refund_target_line_id or line.matched_transaction_id):
            raise serializers.ValidationError({"action": "Bu satır için iptal edilecek bir harcama bulunamadı."})
        if action == StatementLine.Action.MATCH:
            if match is None:
                raise serializers.ValidationError({"matched_transaction": "Eşleştirilecek bekleyen kaydı seçin."})
            if match.account_id != line.statement.account_id or match.kind != line.kind:
                raise serializers.ValidationError({"matched_transaction": "Seçilen kayıt bu satırla uyuşmuyor."})
        category = attrs.get("category", line.category)
        if category and category.kind != line.kind:
            raise serializers.ValidationError({"category": "Kategori türü işlem türüyle uyuşmuyor."})
        return attrs

    def update(self, instance, validated_data):
        action = validated_data.get("action", instance.action)
        if action == StatementLine.Action.SKIP and not instance.skip_reason:
            validated_data["skip_reason"] = StatementLine.SkipReason.USER
        elif action != StatementLine.Action.SKIP:
            validated_data["skip_reason"] = ""
        category_changed = "category" in validated_data and validated_data["category"] != instance.category
        line = super().update(instance, validated_data)
        if category_changed:
            apply_learned_category(line)  # remember merchant -> category, update same-merchant lines
        return line


class MerchantCategoryRuleSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = MerchantCategoryRule
        fields = ["id", "kind", "merchant_key", "category", "category_name", "hits", "updated_at"]
        read_only_fields = fields


class CardCycleItemSerializer(serializers.Serializer):
    """One card statement cycle of an account, shown as a single row in activity lists."""

    type = serializers.CharField()
    date = serializers.DateField()
    account = serializers.UUIDField()
    account_name = serializers.CharField()
    card_name = serializers.CharField()
    statement_day = serializers.IntegerField(allow_null=True)
    start = serializers.DateField()
    end = serializers.DateField()
    count = serializers.IntegerField()
    expense = serializers.DecimalField(max_digits=14, decimal_places=2)
    income = serializers.DecimalField(max_digits=14, decimal_places=2)
    net = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    status = serializers.CharField()  # paid | pending | partial | cancelled
    in_balance = serializers.BooleanField()


def serialize_activity(items, context) -> list[dict]:
    out = []
    for item in items:
        if item["type"] == "transaction":
            out.append({"type": "transaction", "date": item["date"],
                        "transaction": TransactionSerializer(item["transaction"], context=context).data})
        else:
            out.append(CardCycleItemSerializer(item).data)
    return out


class BulkStatusSerializer(serializers.Serializer):
    account = OwnedPrimaryKeyRelatedField(queryset=Account.objects.all())
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    status = serializers.ChoiceField(choices=[Transaction.Status.PAID, Transaction.Status.PENDING])
    paid_on = serializers.DateField(required=False)


class SeriesSerializer(serializers.ModelSerializer):
    """Recurring / installment payments ('Otomatik ödemelerim'). Edited through their next pending occurrence."""

    next_occurrence = serializers.SerializerMethodField()
    paid_count = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()

    class Meta:
        model = Series
        fields = [
            "id", "series_type", "kind", "description", "amount", "total_amount", "installment_count", "frequency",
            "interval", "start_date", "end_date", "account", "category", "auto_pay", "is_card", "is_active",
            "next_occurrence", "paid_count", "pending_count",
        ]
        read_only_fields = fields

    def _occurrences(self, obj):
        return [t for t in obj.transactions.all()]

    def get_next_occurrence(self, obj):
        pending = sorted((t for t in self._occurrences(obj) if t.status == Transaction.Status.PENDING), key=lambda t: t.date)
        return TransactionSerializer(pending[0], context=self.context).data if pending else None

    def get_paid_count(self, obj):
        return sum(1 for t in self._occurrences(obj) if t.status == Transaction.Status.PAID)

    def get_pending_count(self, obj):
        return sum(1 for t in self._occurrences(obj) if t.status == Transaction.Status.PENDING)


class PaySerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    date = serializers.DateField(required=False)


def _money():
    return serializers.DecimalField(max_digits=14, decimal_places=2)


class CardCycleSerializer(serializers.Serializer):
    account = serializers.UUIDField()
    name = serializers.CharField()
    start = serializers.DateField()
    end = serializers.DateField()


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
    card_cycles = CardCycleSerializer(many=True)  # card statement cycles counted in this month
    current_balance = _money()
    overdue_income = _money()
    overdue_expense = _money()
    projected_balance = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
