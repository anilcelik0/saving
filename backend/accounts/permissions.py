from rest_framework.permissions import BasePermission

from .authentication import APP_CLAIM


class AppPermission(BasePermission):
    """Allows access only to authenticated users whose token belongs to `app_slug`."""

    app_slug = None
    message = "Bu işlem uygulamanız için kullanılamaz."

    def has_permission(self, request, view):
        token = request.auth
        return bool(
            request.user
            and request.user.is_authenticated
            and token is not None
            and token.get(APP_CLAIM) == self.app_slug
        )


def app_permission(slug):
    """Usage in client apps: IsSavingUser = app_permission("saving")."""
    return type(f"{slug.title()}AppPermission", (AppPermission,), {"app_slug": slug})
