from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken

TOKEN_INVALID_MESSAGE = "Oturum geçersiz veya süresi dolmuş. Lütfen tekrar giriş yapın."
PROTECTED_MESSAGE = "Bu kayıt başka kayıtlarda kullanıldığı için silinemez. Bunun yerine arşivleyebilirsiniz."


def api_exception_handler(exc, context):
    """DRF handler: Turkish token errors (keeping the code for clients) and 409 for protected deletes."""
    if isinstance(exc, ProtectedError):
        return Response({"detail": PROTECTED_MESSAGE, "code": "protected"}, status=status.HTTP_409_CONFLICT)

    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, InvalidToken):
        response.data = {"detail": TOKEN_INVALID_MESSAGE, "code": "token_not_valid"}
    return response
