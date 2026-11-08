from django.contrib import admin

from .models import Account, Category, PaymentPlan, Transaction


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
    list_display = ["date", "kind", "amount", "description", "category", "account", "source", "plan_sequence", "user"]
    list_filter = ["kind", "source", "date"]
    search_fields = ["description", "user__username"]
    list_select_related = ["category", "account", "user"]
    date_hierarchy = "date"


@admin.register(PaymentPlan)
class PaymentPlanAdmin(admin.ModelAdmin):
    list_display = [
        "description", "plan_type", "kind", "amount", "frequency", "next_due_date",
        "paid_count", "installment_count", "auto_pay", "is_active", "user",
    ]
    list_filter = ["plan_type", "kind", "frequency", "auto_pay", "is_active"]
    search_fields = ["description", "user__username"]
