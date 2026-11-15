from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from . import legal
from .authentication import APP_CLAIM, issue_tokens
from .models import ClientApp, LegalDocument, username_validator

User = get_user_model()


class LegalDocumentSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    url = serializers.SerializerMethodField(help_text="Public web page of the current version")

    class Meta:
        model = LegalDocument
        fields = ["id", "kind", "kind_label", "title", "version", "published_at", "requires_acceptance", "url"]

    def get_url(self, obj):
        return legal.page_url(obj, self.context.get("request"))


class LegalDocumentDetailSerializer(LegalDocumentSerializer):
    body = serializers.SerializerMethodField(help_text="Markdown with placeholders filled")

    class Meta(LegalDocumentSerializer.Meta):
        fields = LegalDocumentSerializer.Meta.fields + ["body"]

    def get_body(self, obj):
        return legal.render_markdown(obj)


class UserSerializer(serializers.ModelSerializer):
    app = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    pending_legal = serializers.SerializerMethodField(
        help_text="Current legal documents the user has not accepted yet; the client asks before continuing"
    )

    class Meta:
        model = User
        fields = ["id", "app", "username", "email", "first_name", "last_name", "date_joined", "pending_legal"]
        read_only_fields = ["id", "app", "username", "email", "date_joined"]

    def get_pending_legal(self, obj):
        return LegalDocumentSerializer(legal.pending_documents(obj), many=True, context=self.context).data


class RegisterSerializer(serializers.Serializer):
    app = serializers.SlugRelatedField(
        slug_field="slug", queryset=ClientApp.objects.filter(is_active=True)
    )
    username = serializers.CharField(max_length=30)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    accepted_documents = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True,
        help_text="Ids of the current legal documents the user accepted (all required ones must be included)",
    )

    def validate(self, attrs):
        attrs["username"] = attrs["username"].strip().lower()
        attrs["email"] = attrs["email"].strip().lower()
        app = attrs["app"]

        errors = {}
        required = legal.required_documents(app)
        accepted_ids = set(attrs.get("accepted_documents") or [])
        if any(doc.pk not in accepted_ids for doc in required):
            names = " ve ".join(doc.get_kind_display() for doc in required)
            errors["accepted_documents"] = [f"Kayıt olmak için {names} onaylanmalı."]
        attrs["accepted_documents"] = [doc for doc in legal.current_documents(app) if doc.pk in accepted_ids]
        try:
            username_validator(attrs["username"])
        except DjangoValidationError as e:
            errors["username"] = e.messages
        if User.objects.filter(app=app, username=attrs["username"]).exists():
            errors["username"] = ["Bu kullanıcı adı zaten alınmış."]
        if User.objects.filter(app=app, email=attrs["email"]).exists():
            errors["email"] = ["Bu e-posta adresi zaten kayıtlı."]

        candidate = User(**{k: v for k, v in attrs.items() if k not in ("password", "accepted_documents")})
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as e:
            errors["password"] = e.messages

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        documents = validated_data.pop("accepted_documents")
        user = User.objects.create_user(password=password, **validated_data)
        legal.record_acceptances(user, documents, self.context.get("request"))
        return user


class ConsentSerializer(serializers.Serializer):
    """Accept current legal documents of the user's app (e.g. after a new version was published)."""

    documents = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)

    def validate_documents(self, value):
        user = self.context["request"].user
        current = {doc.pk: doc for doc in legal.current_documents(user.app)} if user.app_id else {}
        unknown = [str(pk) for pk in value if pk not in current]
        if unknown:
            raise serializers.ValidationError("Bu metin(ler) güncel değil veya bulunamadı. Lütfen sayfayı yenileyin.")
        return [current[pk] for pk in value]


class LoginSerializer(serializers.Serializer):
    app = serializers.SlugField()
    identifier = serializers.CharField(help_text="Kullanıcı adı veya e-posta")
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            self.context.get("request"),
            username=attrs["identifier"],
            password=attrs["password"],
            app=attrs["app"],
        )
        if user is None:
            raise AuthenticationFailed("Kullanıcı adı/e-posta veya şifre hatalı.")
        update_last_login(None, user)
        attrs["user"] = user
        return attrs

    def to_representation(self, instance):
        user = instance["user"]
        return {"user": UserSerializer(user, context=self.context).data, **issue_tokens(user)}


class AppTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh only while the user and its app are still active and match the token's app claim."""

    def validate(self, attrs):
        token = self.token_class(attrs["refresh"])
        user = User.objects.select_related("app").filter(pk=token.get("user_id")).first()
        if (
            user is None
            or not user.is_active
            or user.app is None
            or not user.app.is_active
            or user.app.slug != token.get(APP_CLAIM)
        ):
            raise AuthenticationFailed("Oturum geçersiz. Lütfen tekrar giriş yapın.", code="session_invalid")
        return super().validate(attrs)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
