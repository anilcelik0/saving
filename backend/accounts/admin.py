from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import ClientApp, User


@admin.register(ClientApp)
class ClientAppAdmin(admin.ModelAdmin):
    list_display = ["slug", "name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["slug", "name"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "app", "is_active", "is_staff", "date_joined"]
    list_filter = ["app", "is_active", "is_staff", "is_superuser"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["-date_joined"]
    list_select_related = ["app"]

    fieldsets = [
        (None, {"fields": ["app", "username", "email", "password"]}),
        ("Personal info", {"fields": ["first_name", "last_name"]}),
        ("Permissions", {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        ("Dates", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["app", "username", "email", "password1", "password2"]}),
    ]
