from django.contrib import admin

from .models import Account, Category, Series, StatementImport, StatementLine, Transaction


class StatementLineInline(admin.TabularInline):
    model = StatementLine
    extra = 0
    fields = ["line_no", "date", "description", "kind", "amount", "action", "skip_reason", "category"]
    readonly_fields = fields
    can_delete = False


@admin.register(StatementImport)
class StatementImportAdmin(admin.ModelAdmin):
    list_display = ["original_name", "bank", "statement_type", "status", "period_start", "period_end",
                    "imported_count", "matched_count", "user", "created_at"]
    list_filter = ["status", "bank", "statement_type"]
    search_fields = ["original_name", "user__username"]
    inlines = [StatementLineInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "user", "is_archived"]
    list_filter = ["kind", "is_archived"]
    search_fields = ["name", "user__username"]


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["name", "account_type", "opening_balance", "user", "is_archived"]
    list_filter = ["account_type"]
    search_fields = ["name", "user__username"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["date", "kind", "amount", "status", "auto_pay", "description", "account", "sequence", "user"]
    list_filter = ["kind", "status", "auto_pay", "source", "date"]
    search_fields = ["description", "user__username"]
    list_select_related = ["account", "user"]
    date_hierarchy = "date"


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = [
        "description", "series_type", "kind", "amount", "frequency", "start_date",
        "generated_count", "generated_until", "installment_count", "is_active", "user",
    ]
    list_filter = ["series_type", "kind", "frequency", "is_active"]
    search_fields = ["description", "user__username"]
