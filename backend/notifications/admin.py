from django.contrib import admin

from .models import DeviceToken


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "last_seen", "created_at"]
    list_filter = ["platform", "user__app"]
    search_fields = ["user__username"]
    list_select_related = ["user"]
    readonly_fields = ["user", "token", "platform", "last_seen", "created_at"]

    def has_add_permission(self, request):
        return False
