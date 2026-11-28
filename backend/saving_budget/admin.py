from collections import defaultdict
from datetime import timedelta

from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone

from .models import (
    Account, Category, MerchantCategoryRule, Series, StatementImport, StatementLine, StatementReadLog, Transaction,
)
from .statements.registry import BANK_LABELS


@admin.register(MerchantCategoryRule)
class MerchantCategoryRuleAdmin(admin.ModelAdmin):
    list_display = ["merchant_key", "kind", "category", "hits", "user", "updated_at"]
    list_filter = ["kind"]
    search_fields = ["merchant_key", "user__username"]


class StatementLineInline(admin.TabularInline):
    model = StatementLine
    extra = 0
    fields = ["line_no", "date", "description", "kind", "amount", "installment", "action", "skip_reason",
              "category", "flag_codes"]
    readonly_fields = fields
    can_delete = False

    @admin.display(description="İşaretler")
    def flag_codes(self, obj):
        return ", ".join(f["code"] for f in obj.flags or []) or "-"


@admin.register(StatementImport)
class StatementImportAdmin(admin.ModelAdmin):
    list_display = ["original_name", "bank", "statement_type", "status", "check_status", "period_start", "period_end",
                    "imported_count", "matched_count", "user", "created_at"]
    list_filter = ["status", "check_status", "bank", "statement_type"]
    search_fields = ["original_name", "user__username"]
    readonly_fields = ["check_details", "read_log"]
    inlines = [StatementLineInline]


@admin.register(StatementReadLog)
class StatementReadLogAdmin(admin.ModelAdmin):
    """Every read (anonymous). 'Okuma kalitesi' groups them per bank / statement type / file type."""

    list_display = ["created_at", "bank", "statement_type", "file_type", "engine_version", "status", "check_status",
                    "line_count", "flagged_count", "action_changes", "category_changes", "confirmed_at"]
    list_filter = ["status", "check_status", "bank", "statement_type", "file_type", "engine_version"]
    change_list_template = "admin/saving_budget/statementreadlog/change_list.html"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_urls(self):
        custom = [path("quality/", self.admin_site.admin_view(self.quality_view),
                       name="saving_budget_statementreadlog_quality")]
        return custom + super().get_urls()

    def quality_view(self, request):
        """Reading quality per bank / type / file type (and per engine version): how often the statement's own
        totals confirmed the reading, how many lines needed a look, how much the users changed before importing."""
        days = request.GET.get("days", "90")
        logs = StatementReadLog.objects.all()
        if days.isdigit():
            logs = logs.filter(created_at__gte=timezone.now() - timedelta(days=int(days)))
        if version := request.GET.get("version"):
            logs = logs.filter(engine_version=version)
        groups = defaultdict(list)
        for log in logs:
            groups[(log.bank or "?", log.statement_type or "?", log.file_type or "?")].append(log)
        rows = [_quality_row(BANK_LABELS.get(bank, bank), kind, file_type, items)
                for (bank, kind, file_type), items in groups.items()]
        rows.sort(key=lambda r: (-r["problems"], -r["count"]))
        versions = sorted(set(StatementReadLog.objects.values_list("engine_version", flat=True)), reverse=True)
        context = {
            **self.admin_site.each_context(request), "title": "Ekstre okuma kalitesi", "rows": rows,
            "total": _quality_row("Toplam", "", "", list(logs)) if logs else None, "days": days,
            "versions": versions, "version": version or "", "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/saving_budget/statementreadlog/quality.html", context)


def _percent(part: int, whole: int) -> str:
    return f"%{round(100 * part / whole)}" if whole else "-"


def _quality_row(bank, kind, file_type, logs: list[StatementReadLog]) -> dict:
    read = [x for x in logs if x.status == "ready"]
    confirmed = [x for x in read if x.confirmed_at]
    by_check = defaultdict(int)
    for x in read:
        by_check[x.check_status or "-"] += 1
    lines = sum(x.line_count for x in read)
    confirmed_lines = sum(x.line_count for x in confirmed)
    return {
        "bank": bank, "kind": {"card": "Kart", "account": "Hesap"}.get(kind, kind), "file_type": file_type,
        "count": len(logs), "failed": len(logs) - len(read),
        "ok": by_check["ok"], "ok_rate": _percent(by_check["ok"], len(read)),
        "mismatch": by_check["mismatch"], "unknown": by_check["unknown"],
        "problems": len(logs) - by_check["ok"],
        "avg_lines": round(lines / len(read), 1) if read else "-",
        "flagged_rate": _percent(sum(x.flagged_count for x in read), lines),
        "confirmed": len(confirmed),
        "action_rate": _percent(sum(x.action_changes for x in confirmed), confirmed_lines),
        "category_rate": _percent(sum(x.category_changes for x in confirmed), confirmed_lines),
        "last": max(x.created_at for x in logs),
        "last_problem": max((x.created_at for x in logs if x.status == "failed" or x.check_status != "ok"),
                            default=None),
    }


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
