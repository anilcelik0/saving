from django.contrib import admin

from .models import Move, Run


class MoveInline(admin.TabularInline):
    model = Move
    extra = 0
    can_delete = False
    fields = ["number", "card", "slot", "correct", "timed_out", "elapsed_ms", "created_at"]
    readonly_fields = fields


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "mode", "difficulty", "attribute", "status", "score", "lives"]
    list_filter = ["mode", "status", "difficulty", "attribute"]
    search_fields = ["user__username", "seed"]
    list_select_related = ["user", "attribute"]
    readonly_fields = ["user", "mode", "difficulty", "attribute", "seed", "deck", "line", "next_index", "lives",
                       "target", "status", "dealt_at", "finished_at", "created_at"]
    inlines = [MoveInline]

    def has_add_permission(self, request):
        return False
