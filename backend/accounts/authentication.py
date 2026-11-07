from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

APP_CLAIM = "app"


def issue_tokens(user):
    """Create a refresh/access pair carrying the user's app slug."""
    refresh = RefreshToken.for_user(user)
    refresh[APP_CLAIM] = user.app.slug
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class AppJWTAuthentication(JWTAuthentication):
    """JWT auth that also verifies the token's app claim matches the user's (active) app."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        claim = validated_token.get(APP_CLAIM)
        app = user.app
        if not claim or app is None or app.slug != claim or not app.is_active:
            raise AuthenticationFailed("Bu oturum bu uygulama için geçerli değil.", code="app_mismatch")
        return user
