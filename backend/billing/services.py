"""
Reward intents (ask → watch the ad → AdMob SSV grants), entitlements and RevenueCat webhook events.
A reward is never granted on the client's word: only the signed SSV callback (or, in development, the DEBUG-only
dev grant) calls grant().
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from . import registry
from .models import Entitlement, RewardIntent, StoreEvent

logger = logging.getLogger(__name__)
INTENT_TTL = timedelta(minutes=30)  # an ad is shown right after asking; older pending intents can't be granted


class BillingConflict(APIException):
    status_code = 409
    default_detail = "Bu işlem şu an yapılamaz."
    default_code = "billing_conflict"


# ---------------------------------------------------------------- rewards
def _today_start():
    now = timezone.localtime()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def ads_left_today(user) -> int | None:
    """Rewards the user can still get today in their app (None = no cap)."""
    app = user.app.slug if user.app_id else ""
    cap = registry.daily_cap(app)
    if cap is None:
        return None
    used = RewardIntent.objects.filter(user=user, kind__startswith=f"{app}.", status=RewardIntent.Status.GRANTED,
                                       granted_at__gte=_today_start()).count()
    return max(0, cap - used)


def _kind_for(user, kind: str) -> registry.RewardKind:
    reward = registry.reward_kind(kind)
    if reward is None or not user.app_id or kind.split(".", 1)[0] != user.app.slug:
        raise BillingConflict("Bu ödül bu uygulamada yok.", code="unknown_reward")
    return reward


def create_intent(user, kind: str, ref: str = "") -> RewardIntent:
    reward = _kind_for(user, kind)
    if ads_left_today(user) == 0:
        raise BillingConflict("Bugünlük reklam hakkın bitti. Yarın yine izleyebilirsin.", code="daily_ad_cap")
    try:
        reward.check(user, ref)
    except registry.RewardRefused as e:
        raise BillingConflict(e.message, code=e.code) from None
    return RewardIntent.objects.create(user=user, kind=kind, ref=ref)


def _reject(intent: RewardIntent, detail: str) -> RewardIntent:
    intent.status, intent.detail = RewardIntent.Status.REJECTED, detail[:200]
    intent.save(update_fields=["status", "detail", "transaction_id", "ad_unit", "callback", "updated_at"])
    return intent


@transaction.atomic
def _grant(intent_id, transaction_id: str, user_id: str | None, ad_unit: str = "",
           callback: dict | None = None) -> RewardIntent | None:
    """Idempotent by transaction id; checks the intent again, then applies the registered reward."""
    done = RewardIntent.objects.filter(transaction_id=transaction_id).first()
    if done:
        return done
    try:
        intent_id = uuid.UUID(str(intent_id))
    except ValueError:
        intent_id = None
    locked = RewardIntent.objects.select_for_update(of=("self",)).select_related("user__app")  # user.app is nullable
    intent = locked.filter(pk=intent_id).first() if intent_id else None
    if intent is None:
        logger.warning("SSV for unknown intent %s (tx %s)", intent_id, transaction_id)
        return None
    if intent.status != RewardIntent.Status.PENDING:
        return intent
    intent.transaction_id, intent.ad_unit, intent.callback = transaction_id, ad_unit, callback or {}
    if user_id is not None and user_id != str(intent.user_id):
        return _reject(intent, "user_id does not match the intent")
    if timezone.now() - intent.created_at > INTENT_TTL:
        return _reject(intent, "intent expired")
    reward = registry.reward_kind(intent.kind)
    if reward is None:
        return _reject(intent, "reward kind no longer registered")
    try:
        reward.check(intent.user, intent.ref)
        reward.grant(intent.user, intent.ref)
    except registry.RewardRefused as e:
        return _reject(intent, e.message)
    intent.status, intent.granted_at = RewardIntent.Status.GRANTED, timezone.now()
    intent.save()
    return intent


def grant_from_ssv(params: dict) -> RewardIntent | None:
    """Verified SSV parameters → grant (custom_data = intent id, user_id = our user id)."""
    transaction_id = params.get("transaction_id")
    if not transaction_id:
        return None
    return _grant(params.get("custom_data"), transaction_id, params.get("user_id"),
                  ad_unit=params.get("ad_unit", ""), callback=params)


def grant_dev(user, intent_id) -> RewardIntent | None:
    """Development only (DEBUG): what the SSV callback would do after a test ad."""
    return _grant(intent_id, f"dev-{uuid.uuid4().hex}", str(user.pk), ad_unit="dev")


def intent_payload(intent: RewardIntent) -> dict:
    return {
        "id": str(intent.pk), "kind": intent.kind, "ref": intent.ref, "status": intent.status, "detail": intent.detail,
        "user_id": str(intent.user_id), "custom_data": str(intent.pk),
        "ads_left_today": ads_left_today(intent.user),
    }


# ---------------------------------------------------------------- entitlements
def entitlement(user, key: str = "pro") -> Entitlement | None:
    """The active entitlement, else None."""
    ent = Entitlement.objects.filter(user=user, key=key).first()
    return ent if ent and ent.is_active else None


@transaction.atomic  # own transaction for callers outside one (dev toggle); joins the webhook's otherwise
def set_entitlement(user, key: str, expires_at, source: str, product_id: str = "", store: str = "",
                    event_at=None) -> Entitlement:
    ent, _ = Entitlement.objects.select_for_update().get_or_create(user=user, key=key)
    ent.expires_at, ent.source, ent.product_id, ent.store = expires_at, source, product_id, store
    ent.last_event_at = event_at or ent.last_event_at
    ent.save()
    return ent


# ---------------------------------------------------------------- RevenueCat
GRANTING_EVENTS = {"INITIAL_PURCHASE", "RENEWAL", "PRODUCT_CHANGE", "UNCANCELLATION", "NON_RENEWING_PURCHASE",
                   "SUBSCRIPTION_EXTENDED", "TEMPORARY_ENTITLEMENT_GRANT", "CANCELLATION", "BILLING_ISSUE",
                   "SUBSCRIPTION_PAUSED", "EXPIRATION"}


def _ms(value) -> datetime | None:
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC) if value else None


def _app_user(app_slug: str, user_id):
    try:
        uuid.UUID(str(user_id))
    except ValueError:
        return None
    return get_user_model().objects.filter(pk=user_id, app__slug=app_slug).first()


@transaction.atomic
def handle_revenuecat(app_slug: str, payload: dict) -> str:
    """
    One webhook body. app_user_id = our user id (the client logs in to RevenueCat with it). Each event carries the
    entitlement's expiration; CANCELLATION keeps it until then, EXPIRATION ends it. Older events than the last one
    applied are ignored; the same event id twice is a no-op.
    """
    event = payload.get("event") or {}
    event_id, event_type = str(event.get("id") or ""), str(event.get("type") or "")
    if not event_id:
        return "no event id"
    try:
        with transaction.atomic():
            record = StoreEvent.objects.create(event_id=event_id, event_type=event_type, app_slug=app_slug,
                                               payload=payload)
    except IntegrityError:
        return "duplicate"
    user = _app_user(app_slug, event.get("app_user_id")) or _app_user(app_slug, event.get("original_app_user_id"))
    record.user = user

    if event_type == "TEST":
        result = "test"
    elif event_type == "TRANSFER":
        # purchases moved to another app user: end them on the old users; the new one gets its next event
        for old in event.get("transferred_from") or []:
            old_user = _app_user(app_slug, old)
            for key in settings.BILLING_REVENUECAT_ENTITLEMENTS:
                if old_user and entitlement(old_user, key):
                    set_entitlement(old_user, key, timezone.now(), Entitlement.Source.REVENUECAT)
        result = "transfer"
    elif event_type not in GRANTING_EVENTS:
        result = "ignored"
    elif user is None:
        result = "unknown user"
    else:
        event_at = _ms(event.get("event_timestamp_ms")) or timezone.now()
        expires = _ms(event.get("expiration_at_ms"))
        if event_type == "EXPIRATION":
            expires = min(expires or event_at, timezone.now())
        keys = [k for k in event.get("entitlement_ids") or [] if k in settings.BILLING_REVENUECAT_ENTITLEMENTS]
        applied = []
        for key in keys:
            current = Entitlement.objects.select_for_update().filter(user=user, key=key).first()
            if current and current.last_event_at and current.last_event_at > event_at:
                continue  # an older event arriving late
            set_entitlement(user, key, expires, Entitlement.Source.REVENUECAT,
                            product_id=str(event.get("product_id") or ""), store=str(event.get("store") or ""),
                            event_at=event_at)
            applied.append(key)
        result = f"applied {','.join(applied)}" if applied else "no matching entitlement"
    record.result = result
    record.save(update_fields=["user", "result", "updated_at"])
    return result
