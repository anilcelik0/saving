from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from rest_framework import generics, serializers, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from . import legal, lifecycle
from .authentication import issue_tokens
from .models import ClientApp, LegalAcceptance
from .serializers import (
    ConsentSerializer, GuestClaimSerializer, GuestRegisterSerializer, LegalDocumentDetailSerializer, LegalDocumentSerializer, LoginSerializer, LogoutSerializer,
    PasswordConfirmSerializer, RegisterSerializer, UserSerializer,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Bu işlem şu an yapılamaz."
    default_code = "conflict"


class PublicAuthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def get_authenticate_header(self, request):
        # Without authenticators DRF turns 401 into 403; keep 401 for bad credentials.
        return 'Bearer realm="api"'


class RegisterView(PublicAuthView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"user": UserSerializer(user, context={"request": request}).data, **issue_tokens(user)},
            status=status.HTTP_201_CREATED,
        )


class GuestRegisterView(PublicAuthView):
    """POST {"app", "accepted_documents"}: guest account for apps with allow_guests (e.g. lineup)."""

    throttle_scope = "guest"

    def post(self, request):
        serializer = GuestRegisterSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "user": UserSerializer(user, context={"request": request}).data,
                "credentials": {"username": user.username, "password": user.generated_password},
                **issue_tokens(user),
            },
            status=status.HTTP_201_CREATED,
        )


class GuestClaimView(APIView):
    """
    POST {email, password, username?} (signed-in guest): the account becomes a regular one with the same data.
    The guest's other sessions are signed out; a fresh token pair is returned.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @transaction.atomic
    def post(self, request):
        if not request.user.is_guest:
            raise Conflict("Bu hesap zaten kayıtlı.", code="not_guest")
        serializer = GuestClaimSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        lifecycle.revoke_sessions(user)
        return Response({"user": UserSerializer(user, context={"request": request}).data, **issue_tokens(user)})


class LoginView(PublicAuthView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class LogoutView(APIView):
    """Blacklists the given refresh token."""

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass  # already invalid/blacklisted: logout is idempotent
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


# ---------------------------------------------------------------- account lifecycle
class _AccountActionView(APIView):
    """POST {"password"}: confirm with the password, change the status, sign out every device."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
    action = None

    def post(self, request):
        PasswordConfirmSerializer(data=request.data, context={"request": request}).is_valid(raise_exception=True)
        type(self).action(request.user)
        return Response(UserSerializer(request.user, context={"request": request}).data)


class AccountDeactivateView(_AccountActionView):
    """Freeze: data kept, client app APIs closed until the user logs in and reopens the account."""

    action = staticmethod(lifecycle.deactivate)


class AccountDeleteView(_AccountActionView):
    """Request deletion: locked now, deleted for good after the grace period (login offers to cancel)."""

    action = staticmethod(lifecycle.request_deletion)


class AccountReactivateView(APIView):
    """Reopen a frozen account / cancel a pending deletion (after logging in again)."""

    def post(self, request):
        lifecycle.reactivate(request.user)
        return Response(UserSerializer(request.user, context={"request": request}).data)


# ---------------------------------------------------------------- legal documents
def _active_app(slug) -> ClientApp:
    return get_object_or_404(ClientApp, slug=slug, is_active=True)


class LegalDocumentListView(APIView):
    """Public: current legal documents of an app (register screen shows them with checkboxes)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, app):
        docs = legal.current_documents(_active_app(app))
        return Response(LegalDocumentSerializer(docs, many=True, context={"request": request}).data)


class LegalDocumentDetailView(APIView):
    """Public: current version of one document, Markdown body."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, app, kind):
        doc = next((d for d in legal.current_documents(_active_app(app)) if d.kind == kind), None)
        if doc is None:
            raise Http404
        return Response(LegalDocumentDetailSerializer(doc, context={"request": request}).data)


class ConsentView(APIView):
    """
    GET: the user's state for each current document (accepted version/date) + pending ones.
    POST {"documents": [ids]}: accept current documents (new versions).
    """

    def _state(self, request):
        user = request.user
        current = legal.current_documents(user.app) if user.app_id else []
        acceptances = (
            LegalAcceptance.objects.filter(user=user, document__kind__in=[d.kind for d in current],
                                           document__app_id=user.app_id)
            .select_related("document").order_by("document__kind", "-document__version")
        )
        latest = {}
        for a in acceptances:
            latest.setdefault(a.document.kind, a)  # highest accepted version per kind
        context = {"request": request}
        as_local = serializers.DateTimeField().to_representation  # same format/time zone as other fields
        documents = []
        for doc in current:
            a = latest.get(doc.kind)
            documents.append({
                **LegalDocumentSerializer(doc, context=context).data,
                "accepted_version": a.document.version if a else None,
                "accepted_at": as_local(a.accepted_at) if a else None,
                "is_accepted": bool(a and a.document_id == doc.pk),
            })
        pending = legal.pending_documents(user)
        return {"documents": documents, "pending": LegalDocumentSerializer(pending, many=True, context=context).data}

    def get(self, request):
        return Response(self._state(request))

    def post(self, request):
        serializer = ConsentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        legal.record_acceptances(request.user, serializer.validated_data["documents"], request)
        return Response(self._state(request))


def legal_page(request, app, kind):
    """Public web page of the current version (privacy policy URL for Google Play)."""
    doc = next((d for d in legal.current_documents(_active_app(app)) if d.kind == kind), None)
    if doc is None:
        raise Http404
    return render(request, "accounts/legal_document.html",
                  {"app": doc.app, "doc": doc, "body": legal.render_html(doc)})


WEB_DELETE_MAX_ATTEMPTS, WEB_DELETE_LOCK_SECONDS = 10, 15 * 60


def delete_account_page(request, app):
    """
    Public web page to request account deletion without the app (Google Play requirement). Same effect as
    Diğer > Hesabı sil: locked now, deleted after the grace period unless the user logs in and cancels.
    """
    client_app = _active_app(app)
    context = {"app": client_app, "grace_days": settings.ACCOUNT_DELETION_GRACE_DAYS, "identifier": ""}
    if request.method == "POST":
        key = f"web-delete-attempts:{legal.client_ip(request) or 'unknown'}"
        attempts = cache.get(key, 0)
        identifier = (request.POST.get("identifier") or "").strip()
        context["identifier"] = identifier
        if attempts >= WEB_DELETE_MAX_ATTEMPTS:
            context["error"] = "Çok fazla hatalı deneme yapıldı. Lütfen 15 dakika sonra tekrar deneyin."
        elif not request.POST.get("confirm"):
            context["error"] = "Devam etmek için onay kutusunu işaretleyin."
        else:
            user = authenticate(request, username=identifier, password=request.POST.get("password", ""), app=app)
            if user is None:
                cache.set(key, attempts + 1, WEB_DELETE_LOCK_SECONDS)
                context["error"] = "Kullanıcı adı/e-posta veya şifre hatalı."
            else:
                lifecycle.request_deletion(user)
                context.update(done=True, delete_after=user.delete_after)
    return render(request, "accounts/delete_account.html", context)
