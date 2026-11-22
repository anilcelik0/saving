from django.contrib import admin
from django.db.models import Count

from .models import DailyPlay, DailyPuzzle, Energy, Move, Run


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


class DailyPlayInline(admin.TabularInline):
    model = DailyPlay
    extra = 0
    can_delete = False
    fields = ["user", "status", "attempts", "finished_at"]
    readonly_fields = fields


@admin.register(DailyPuzzle)
class DailyPuzzleAdmin(admin.ModelAdmin):
    """Created by the first request of the day; frozen afterwards."""

    list_display = ["number", "date", "attribute", "plays"]
    list_select_related = ["attribute"]
    readonly_fields = ["date", "number", "attribute", "seed", "deck", "created_at"]
    inlines = [DailyPlayInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(play_count=Count("plays"))

    @admin.display(description="oyun", ordering="play_count")
    def plays(self, obj):
        return obj.play_count

    def has_add_permission(self, request):
        return False
