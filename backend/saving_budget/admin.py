from django.contrib import admin

from .models import Account, Category, GoalContribution, RecurringPayment, SavingGoal, Transaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "user", "is_archived"]
    list_filter = ["kind", "is_archived"]
    search_fields = ["name", "user__username"]


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["name", "account_type", "bank", "user", "is_archived"]
    list_filter = ["account_type", "bank"]
    search_fields = ["name", "user__username"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["date", "kind", "amount", "description", "category", "account", "source", "user"]
    list_filter = ["kind", "source", "date"]
    search_fields = ["description", "user__username"]
    list_select_related = ["category", "account", "user"]
    date_hierarchy = "date"


@admin.register(RecurringPayment)
class RecurringPaymentAdmin(admin.ModelAdmin):
    list_display = ["name", "amount", "frequency", "next_due_date", "paid_count", "installment_count", "is_active", "user"]
    list_filter = ["frequency", "is_active"]
    search_fields = ["name", "user__username"]


class GoalContributionInline(admin.TabularInline):
    model = GoalContribution
    extra = 0


@admin.register(SavingGoal)
class SavingGoalAdmin(admin.ModelAdmin):
    list_display = ["name", "target_amount", "target_date", "status", "user"]
    list_filter = ["status"]
    search_fields = ["name", "user__username"]
    inlines = [GoalContributionInline]
