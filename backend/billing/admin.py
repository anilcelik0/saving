from django.contrib import admin

from .models import Entitlement, RewardIntent, StoreEvent


@admin.register(RewardIntent)
class RewardIntentAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "kind", "status", "granted_at", "detail"]
    list_filter = ["status", "kind"]
    search_fields = ["user__username", "transaction_id", "ref"]
    list_select_related = ["user"]
    readonly_fields = ["user", "kind", "ref", "status", "detail", "transaction_id", "ad_unit", "callback",
                       "granted_at", "created_at"]

    def has_add_permission(self, request):
        return False


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    """Store entitlements come from RevenueCat; an admin can also give one (e.g. Pro for a tester)."""

    list_display = ["user", "key", "expires_at", "active", "source", "product_id", "updated_at"]
    list_filter = ["key", "source"]
    search_fields = ["user__username", "user__email"]
    list_select_related = ["user"]
    autocomplete_fields = ["user"]
    readonly_fields = ["last_event_at", "created_at", "updated_at"]

    @admin.display(boolean=True, description="aktif")
    def active(self, obj):
        return obj.is_active


@admin.register(StoreEvent)
class StoreEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "provider", "event_type", "app_slug", "user", "result"]
    list_filter = ["provider", "event_type", "app_slug"]
    search_fields = ["event_id", "user__username"]
    readonly_fields = ["provider", "event_id", "event_type", "app_slug", "user", "result", "payload", "created_at"]

    def has_add_permission(self, request):
        return False
