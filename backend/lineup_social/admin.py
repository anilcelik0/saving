from django.contrib import admin

from .models import Challenge, ChallengeEntry, ChallengeInvite


class EntryInline(admin.TabularInline):
    model = ChallengeEntry
    extra = 0
    can_delete = False
    fields = ["user", "run", "notified", "created_at"]
    readonly_fields = fields


class InviteInline(admin.TabularInline):
    model = ChallengeInvite
    extra = 0
    can_delete = False
    fields = ["user", "created_at"]
    readonly_fields = fields


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ["code", "creator", "created_at", "expires_at"]
    search_fields = ["code", "creator__username"]
    list_select_related = ["creator"]
    readonly_fields = ["code", "creator", "source_run", "created_at"]
    inlines = [InviteInline, EntryInline]

    def has_add_permission(self, request):
        return False
