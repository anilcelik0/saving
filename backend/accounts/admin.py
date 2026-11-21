from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone

from . import lifecycle
from .models import ClientApp, LegalAcceptance, LegalDocument, User


@admin.register(ClientApp)
class ClientAppAdmin(admin.ModelAdmin):
    list_display = ["slug", "name", "is_active", "allow_guests", "created_at"]
    list_filter = ["is_active", "allow_guests"]
    search_fields = ["slug", "name"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "app", "is_guest", "account_status", "delete_after", "is_staff",
                    "date_joined"]
    list_filter = ["app", "is_guest", "account_status", "is_active", "is_staff", "is_superuser"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["-date_joined"]
    list_select_related = ["app"]

    fieldsets = [
        (None, {"fields": ["app", "username", "email", "is_guest", "password"]}),
        ("Personal info", {"fields": ["first_name", "last_name"]}),
        ("Permissions", {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        ("Dates", {"fields": ["last_login", "date_joined"]}),
        ("Hesap durumu", {"fields": ["account_status", "status_changed_at", "delete_after"]}),
    ]
    readonly_fields = ["status_changed_at"]
    actions = ["schedule_deletion", "delete_now"]

    @admin.action(description="Silme talebi oluştur (30 gün sonra silinir, oturumlar kapanır)")
    def schedule_deletion(self, request, queryset):
        for user in queryset.filter(app__isnull=False):
            lifecycle.request_deletion(user)
        self.message_user(request, "Silme talepleri oluşturuldu.", messages.SUCCESS)

    # the standard delete page refuses users with data (Transaction/Series -> Account are PROTECT);
    # this uses the same ordered cleanup as the scheduled deletion
    @admin.action(description="Tüm verileriyle HEMEN kalıcı sil (geri alınamaz)")
    def delete_now(self, request, queryset):
        count = 0
        for user in queryset.filter(app__isnull=False):
            lifecycle.delete_account(user)
            count += 1
        self.message_user(request, f"{count} hesap kalıcı olarak silindi.", messages.WARNING)

    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": ["app", "username", "email", "password1", "password2"]}),
    ]


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    """Drafts are editable; published versions are frozen (users accepted exactly that text)."""

    list_display = ["app", "kind", "version", "title", "published_at", "requires_acceptance"]
    list_filter = ["app", "kind"]
    fields = ["app", "kind", "version", "title", "body", "requires_acceptance", "published_at"]
    readonly_fields = ["version", "published_at"]
    actions = ["publish", "new_version"]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_published:
            return self.fields
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return obj is None or not obj.is_published

    @admin.action(description="Yayınla (kullanıcılardan onay istenir)")
    def publish(self, request, queryset):
        count = queryset.filter(published_at__isnull=True).update(published_at=timezone.now())
        self.message_user(request, f"{count} taslak yayınlandı.", messages.SUCCESS)

    @admin.action(description="Yeni sürüm taslağı oluştur (kopyala)")
    def new_version(self, request, queryset):
        for doc in queryset:
            LegalDocument.objects.create(app=doc.app, kind=doc.kind, title=doc.title, body=doc.body,
                                         requires_acceptance=doc.requires_acceptance)
        self.message_user(request, "Taslak sürüm(ler) oluşturuldu; düzenleyip yayınlayın.", messages.SUCCESS)


@admin.register(LegalAcceptance)
class LegalAcceptanceAdmin(admin.ModelAdmin):
    """Read-only consent log (proof of acceptance)."""

    list_display = ["user", "document", "accepted_at", "ip_address"]
    list_filter = ["document__app", "document__kind", "document__version"]
    search_fields = ["user__username", "user__email"]
    list_select_related = ["user", "document", "document__app"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
