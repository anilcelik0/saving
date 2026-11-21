from django.contrib import admin

from .models import Energy, Move, Run


class MoveInline(admin.TabularInline):
    model = Move
    extra = 0
    can_delete = False
    fields = ["number", "card", "slot", "guess", "correct", "elapsed_ms", "created_at"]
    readonly_fields = fields


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "mode", "difficulty", "attribute", "status", "score", "lives"]
    list_filter = ["mode", "status", "difficulty", "attribute"]
    search_fields = ["user__username", "seed"]
    list_select_related = ["user", "attribute"]
    readonly_fields = ["user", "mode", "difficulty", "attribute", "seed", "deck", "line", "next_index", "lives",
                       "target", "score", "continues_used", "status", "dealt_at", "finished_at", "created_at"]
    inlines = [MoveInline]

    def has_add_permission(self, request):
        return False


@admin.register(Energy)
class EnergyAdmin(admin.ModelAdmin):
    """Stored points as of `since`; the live value adds the refill periods passed since then."""

    list_display = ["user", "stored", "since", "updated_at"]
    search_fields = ["user__username"]
    list_select_related = ["user"]
    readonly_fields = ["user", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False
