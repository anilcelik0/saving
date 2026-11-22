import hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import admob, services
from .models import Entitlement, RewardIntent

logger = logging.getLogger(__name__)


class IntentSerializer(serializers.Serializer):
    kind = serializers.CharField(max_length=50)
    ref = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class RewardIntentListView(APIView):
    """POST {kind, ref}: ask for a reward before showing a rewarded ad (409 daily_ad_cap / the reward's own codes)."""

    def post(self, request):
        data = IntentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        intent = services.create_intent(request.user, data.validated_data["kind"], data.validated_data["ref"])
        return Response(services.intent_payload(intent), status=status.HTTP_201_CREATED)


class RewardIntentDetailView(APIView):
    """GET: pending → granted / rejected once the SSV callback arrived (the client polls for a few seconds)."""

    def get(self, request, pk):
        intent = RewardIntent.objects.filter(user=request.user, pk=pk).first()
        if intent is None:
            raise NotFound("Ödül bulunamadı.", code="reward_not_found")
        return Response(services.intent_payload(intent))


class AdMobSSVView(APIView):
    """
    Public GET called by AdMob after a rewarded ad (callback URL set on the ad unit). 200 for every validly signed
    callback, also when the reward is refused (AdMob would otherwise retry); 403 for a bad signature.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            params = admob.verify(request.META.get("QUERY_STRING", ""))
        except admob.SSVError as e:
            logger.warning("AdMob SSV refused: %s", e)
            return Response({"detail": "Geçersiz imza."}, status=status.HTTP_403_FORBIDDEN)
        if not params.get("custom_data"):  # AdMob's own "verify URL" test call
            return Response({"ok": True})
        intent = services.grant_from_ssv(params)
        return Response({"ok": True, "status": intent.status if intent else "unknown"})


class RevenueCatWebhookView(APIView):
    """Public POST from RevenueCat; the Authorization header must equal the app's configured secret."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, app):
        secret = settings.BILLING_REVENUECAT_WEBHOOK_SECRETS.get(app)
        if not secret:
            raise Http404
        if not hmac.compare_digest(request.headers.get("Authorization", "").encode(), secret.encode()):
            return Response({"detail": "Yetkisiz."}, status=status.HTTP_401_UNAUTHORIZED)
        result = services.handle_revenuecat(app, request.data if isinstance(request.data, dict) else {})
        return Response({"ok": True, "result": result})


class EntitlementView(APIView):
    """GET: the user's active entitlements, e.g. {"pro": {"active": true, "expires_at": ...}}."""

    def get(self, request):
        data = {}
        for ent in Entitlement.objects.filter(user=request.user):
            data[ent.key] = {"active": ent.is_active, "expires_at": ent.expires_at, "source": ent.source}
        return Response(data)


# ---------------------------------------------------------------- development only (BILLING_DEV_TOOLS)
class _DevView(APIView):
    def initial(self, request, *args, **kwargs):
        if not settings.BILLING_DEV_TOOLS:
            raise Http404
        super().initial(request, *args, **kwargs)


class DevGrantView(_DevView):
    """POST: grant a pending intent as if AdMob had called back (test ads never reach a dev PC)."""

    def post(self, request, pk):
        if not RewardIntent.objects.filter(user=request.user, pk=pk).exists():
            raise NotFound("Ödül bulunamadı.", code="reward_not_found")
        return Response(services.intent_payload(services.grant_dev(request.user, pk)))


class DevEntitlementView(_DevView):
    """POST {key, days}: give (days > 0) or take (0) an entitlement, e.g. try Pro without a store."""

    def post(self, request):
        key = str(request.data.get("key") or "pro")
        days = int(request.data.get("days") or 0)
        expires = timezone.now() + timedelta(days=days) if days > 0 else timezone.now()
        ent = services.set_entitlement(request.user, key, expires, Entitlement.Source.DEV)
        return Response({key: {"active": ent.is_active, "expires_at": ent.expires_at, "source": ent.source}})
