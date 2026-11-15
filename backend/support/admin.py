import json

from django.contrib import admin, messages
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import IssueAttachment, IssueReport


class IssueAttachmentInline(admin.TabularInline):
    model = IssueAttachment
    extra = 0
    can_delete = False
    fields = ["download", "size_kb", "source", "created_at", "deleted_at"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Dosya")
    def download(self, obj):
        if not obj.file:
            return f"{obj.original_name} (silindi)"
        url = reverse("support-attachment-download", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.original_name)

    @admin.display(description="Boyut")
    def size_kb(self, obj):
        return f"{obj.size / 1024:.0f} KB"


@admin.register(IssueReport)
class IssueReportAdmin(admin.ModelAdmin):
    """Reports from testers/users. Edit status + response (the user sees the response in the app)."""

    list_display = ["created_at", "category", "status", "short_message", "user", "app", "files"]
    list_filter = ["status", "category", "app"]
    search_fields = ["message", "user__username", "user__email"]
    list_select_related = ["user", "app"]
    fields = [
        "user", "app", "category", "created_at", "message", "context_display", "related_type", "related_id",
        "related_display", "attachments_consent_at", "status", "response", "responded_at", "resolved_at",
    ]
    readonly_fields = [
        "user", "app", "category", "created_at", "message", "context_display", "related_type", "related_id",
        "related_display", "attachments_consent_at", "responded_at", "resolved_at",
    ]
    inlines = [IssueAttachmentInline]
    actions = ["mark_in_progress", "mark_resolved"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(file_count=Count("attachments"))

    def has_add_permission(self, request):
        return False

    @admin.display(description="Mesaj")
    def short_message(self, obj):
        return obj.message[:80] + ("…" if len(obj.message) > 80 else "")

    @admin.display(description="Dosya", ordering="file_count")
    def files(self, obj):
        return obj.file_count or ""

    @admin.display(description="Teknik bilgi")
    def context_display(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.context, ensure_ascii=False, indent=2))

    @admin.display(description="Bağlı kayıt (bildirim anındaki hâli)")
    def related_display(self, obj):
        if not obj.related_snapshot:
            return "-"
        return format_html("<pre>{}</pre>", json.dumps(obj.related_snapshot, ensure_ascii=False, indent=2))

    def save_model(self, request, obj, form, change):
        now = timezone.now()
        if "response" in form.changed_data:
            obj.responded_at = now if obj.response else None
        obj.resolved_at = (obj.resolved_at or now) if obj.is_done else None
        super().save_model(request, obj, form, change)

    @admin.action(description="İnceleniyor olarak işaretle")
    def mark_in_progress(self, request, queryset):
        count = queryset.update(status=IssueReport.Status.IN_PROGRESS, resolved_at=None)
        self.message_user(request, f"{count} bildirim güncellendi.", messages.SUCCESS)

    @admin.action(description="Çözüldü olarak işaretle (ekler gece silinir)")
    def mark_resolved(self, request, queryset):
        count = queryset.update(status=IssueReport.Status.RESOLVED, resolved_at=timezone.now())
        self.message_user(request, f"{count} bildirim çözüldü.", messages.SUCCESS)
