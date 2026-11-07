from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class AppScopedBackend(ModelBackend):
    """
    Authenticates by (username or email) + password within a client app.
    Without `app`, only platform accounts (app=NULL) can authenticate, e.g. Django admin.
    """

    def authenticate(self, request, username=None, password=None, app=None, **kwargs):
        if not username or password is None:
            return None

        User = get_user_model()
        identifier = username.strip().lower()
        field = "email" if "@" in identifier else "username"
        qs = User.objects.filter(**{field: identifier})
        if app:
            qs = qs.filter(app__slug=app, app__is_active=True)
        else:
            qs = qs.filter(app__isnull=True)

        user = qs.first()
        if user is None:
            User().set_password(password)  # mitigate timing-based user enumeration
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
