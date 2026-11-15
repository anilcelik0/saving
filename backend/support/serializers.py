import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from . import registry
from .models import IssueAttachment, IssueReport

ALLOWED_EXTENSIONS = {"pdf", "xlsx", "xls", "csv", "png", "jpg", "jpeg", "webp", "txt", "log"}
CONTEXT_MAX_CHARS = 4000


class IssueAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = IssueAttachment
        fields = ["id", "original_name", "size", "source", "deleted_at"]


class IssueReportSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    attachments = IssueAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = IssueReport
        fields = [
            "id", "category", "category_label", "message", "status", "status_label", "response", "responded_at",
            "related_type", "related_id", "attachments", "created_at",
        ]


class IssueCreateSerializer(serializers.Serializer):
    """
    Multipart (with files) or JSON. Files come from the view via context["files"] = [(UploadedFile, source)]:
    `attachments` (any number up to the limit) and `statement_file` (the statement re-sent from the device).
    """

    category = serializers.ChoiceField(choices=IssueReport.Category.choices)
    message = serializers.CharField(max_length=4000)
    context = serializers.JSONField(required=False)
    related_type = serializers.CharField(required=False, allow_blank=True, max_length=50)
    related_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    attachments_consent = serializers.BooleanField(required=False, default=False)

    def validate_message(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Lütfen sorunu birkaç kelimeyle anlatın.")
        return value.strip()

    def validate_context(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Geçersiz teknik bilgi.")
        if len(json.dumps(value, ensure_ascii=False)) > CONTEXT_MAX_CHARS:
            raise serializers.ValidationError("Teknik bilgi çok uzun.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        files = self.context.get("files", [])
        errors = {}
        if user.app_id is None:
            raise serializers.ValidationError("Bu hesapla bildirim gönderilemez.")

        max_files, max_mb = settings.ISSUE_ATTACHMENT_MAX_FILES, settings.ISSUE_ATTACHMENT_MAX_MB
        if len(files) > max_files:
            errors["attachments"] = [f"En fazla {max_files} dosya eklenebilir."]
        for f, _ in files:
            ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
            if ext not in ALLOWED_EXTENSIONS:
                errors["attachments"] = [f"'{f.name}' eklenemez. İzin verilenler: PDF, Excel, CSV, resim, metin."]
            elif f.size > max_mb * 1024 * 1024:
                errors["attachments"] = [f"'{f.name}' en fazla {max_mb} MB olabilir."]
        if files and not attrs.get("attachments_consent"):
            errors["attachments_consent"] = ["Dosyaların inceleme için gönderilmesini onaylamalısınız."]

        related_type, related_id = attrs.get("related_type") or "", attrs.get("related_id") or ""
        attrs["related_snapshot"] = {}
        if related_type or related_id:
            snapshot = (registry.related_snapshot(user, related_type, related_id)
                        if related_type in registry.related_types() and related_id else None)
            if snapshot is None:
                errors["related_id"] = ["Bildirime bağlanan kayıt bulunamadı."]
            else:
                attrs["related_snapshot"] = snapshot
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        files = self.context.get("files", [])
        report = IssueReport.objects.create(
            user=user,
            app_id=user.app_id,
            category=validated_data["category"],
            message=validated_data["message"],
            context=validated_data.get("context") or {},
            related_type=validated_data.get("related_type") or "",
            related_id=validated_data.get("related_id") or "",
            related_snapshot=validated_data["related_snapshot"],
            attachments_consent_at=timezone.now() if files else None,
        )
        for f, source in files:
            IssueAttachment.objects.create(
                report=report, file=f, original_name=f.name[:255], content_type=(f.content_type or "")[:100],
                size=f.size, source=source,
            )
        return report
