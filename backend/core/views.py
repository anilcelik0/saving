from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def assetlinks(request):
    """Digital Asset Links for every client app with a package + certificate (Android App Links verification)."""
    statements = [
        {"relation": ["delegate_permission/common.handle_all_urls"],
         "target": {"namespace": "android_app", "package_name": cfg["package"],
                    "sha256_cert_fingerprints": cfg["sha256"]}}
        for cfg in settings.ANDROID_APP_LINKS.values() if cfg["sha256"]
    ]
    return JsonResponse(statements, safe=False)


def health(request):
    checks = {"database": True, "cache": True}
    try:
        connection.ensure_connection()
    except Exception:
        checks["database"] = False
    try:
        cache.set("health", "ok", 5)
        checks["cache"] = cache.get("health") == "ok"
    except Exception:
        checks["cache"] = False

    healthy = all(checks.values())
    return Response({"status": "ok" if healthy else "degraded", **checks}, status=200 if healthy else 503)
