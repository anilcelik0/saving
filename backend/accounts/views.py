from django.http import Http404
from django.shortcuts import get_object_or_404, render
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from . import legal
from .authentication import issue_tokens
from .models import ClientApp, LegalAcceptance
from .serializers import (
    ConsentSerializer, LegalDocumentDetailSerializer, LegalDocumentSerializer, LoginSerializer, LogoutSerializer,
    RegisterSerializer, UserSerializer,
)


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
    return render(request, "accounts/legal_document.html", {"doc": doc, "body": legal.render_html(doc)})
