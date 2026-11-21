from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AccountDeactivateView, AccountDeleteView, AccountReactivateView, ConsentView, GuestRegisterView, LoginView,
    LogoutView, MeView, RegisterView,
)

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("guest/", GuestRegisterView.as_view(), name="guest"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("consents/", ConsentView.as_view(), name="consents"),
    path("account/deactivate/", AccountDeactivateView.as_view(), name="account-deactivate"),
    path("account/delete/", AccountDeleteView.as_view(), name="account-delete"),
    path("account/reactivate/", AccountReactivateView.as_view(), name="account-reactivate"),
]
