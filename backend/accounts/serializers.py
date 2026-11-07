from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from .authentication import APP_CLAIM, issue_tokens
from .models import ClientApp, username_validator

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    app = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = User
        fields = ["id", "app", "username", "email", "first_name", "last_name", "date_joined"]
        read_only_fields = ["id", "app", "username", "email", "date_joined"]


class RegisterSerializer(serializers.Serializer):
    app = serializers.SlugRelatedField(
        slug_field="slug", queryset=ClientApp.objects.filter(is_active=True)
    )
    username = serializers.CharField(max_length=30)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate(self, attrs):
        attrs["username"] = attrs["username"].strip().lower()
        attrs["email"] = attrs["email"].strip().lower()
        app = attrs["app"]

        errors = {}
        try:
            username_validator(attrs["username"])
        except DjangoValidationError as e:
            errors["username"] = e.messages
        if User.objects.filter(app=app, username=attrs["username"]).exists():
            errors["username"] = ["Bu kullanıcı adı zaten alınmış."]
        if User.objects.filter(app=app, email=attrs["email"]).exists():
            errors["email"] = ["Bu e-posta adresi zaten kayıtlı."]

        candidate = User(**{k: v for k, v in attrs.items() if k != "password"})
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as e:
            errors["password"] = e.messages

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


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
        return {"user": UserSerializer(user).data, **issue_tokens(user)}


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
