from rest_framework.views import exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken

TOKEN_INVALID_MESSAGE = "Oturum geçersiz veya süresi dolmuş. Lütfen tekrar giriş yapın."


def api_exception_handler(exc, context):
    """DRF handler: unify simplejwt token errors into one Turkish message, keeping the code for clients."""
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, InvalidToken):
        response.data = {"detail": TOKEN_INVALID_MESSAGE, "code": "token_not_valid"}
    return response
