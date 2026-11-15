"""Legal documents (privacy policy, KVKK notice): current versions, rendering, acceptance records."""

import ipaddress

import markdown
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import ClientApp, LegalAcceptance, LegalDocument


def current_documents(app: ClientApp) -> list[LegalDocument]:
    """Latest published version of each document kind of the app."""
    latest = {}
    for doc in LegalDocument.objects.filter(app=app, published_at__isnull=False).select_related("app"):
        if doc.kind not in latest or doc.version > latest[doc.kind].version:
            latest[doc.kind] = doc
    order = {kind: i for i, kind in enumerate(LegalDocument.Kind.values)}
    return sorted(latest.values(), key=lambda d: order.get(d.kind, 99))


def required_documents(app: ClientApp) -> list[LegalDocument]:
    return [doc for doc in current_documents(app) if doc.requires_acceptance]


def pending_documents(user) -> list[LegalDocument]:
    """Current documents the user still has to accept (none for platform accounts)."""
    if user.app_id is None:
        return []
    required = required_documents(user.app)
    accepted = set(
        LegalAcceptance.objects.filter(user=user, document__in=required).values_list("document_id", flat=True)
    )
    return [doc for doc in required if doc.pk not in accepted]


def client_ip(request) -> str | None:
    """Real client IP: nginx puts Cloudflare's CF-Connecting-IP (or the peer address) into X-Real-IP."""
    if request is None:
        return None
    for value in (request.META.get("HTTP_X_REAL_IP"), request.META.get("REMOTE_ADDR")):
        try:
            return str(ipaddress.ip_address((value or "").strip()))
        except ValueError:
            continue
    return None


def record_acceptances(user, documents, request=None) -> None:
    ip = client_ip(request)
    agent = (request.META.get("HTTP_USER_AGENT", "") if request else "")[:300]
    for doc in documents:
        LegalAcceptance.objects.get_or_create(
            user=user, document=doc, defaults={"ip_address": ip, "user_agent": agent}
        )


def render_markdown(doc: LegalDocument) -> str:
    """Body with placeholders filled from settings (LEGAL_CONTROLLER_NAME, LEGAL_CONTACT_EMAIL)."""
    values = {
        "controller": settings.LEGAL_CONTROLLER_NAME or "[veri sorumlusu]",
        "email": settings.LEGAL_CONTACT_EMAIL or "[e-posta]",
        "app": doc.app.name,
        "version": str(doc.version),
        "date": timezone.localtime(doc.published_at).strftime("%d.%m.%Y") if doc.published_at else "",
    }
    text = doc.body
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def render_html(doc: LegalDocument) -> str:
    """Admin-authored Markdown -> HTML for the public page."""
    return markdown.markdown(render_markdown(doc), extensions=["extra", "sane_lists"])


def page_url(doc: LegalDocument, request=None) -> str:
    path = reverse("legal-page", args=[doc.app.slug, doc.kind])
    return request.build_absolute_uri(path) if request else path
