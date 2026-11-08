import asyncio
from collections.abc import Awaitable, Callable

import httpx

NETWORK_ERROR = "Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edin."
SESSION_EXPIRED = "Oturumunuzun süresi doldu. Lütfen tekrar giriş yapın."

# Human-readable labels for field-level validation errors returned by the API.
FIELD_LABELS = {
    "username": "Kullanıcı adı",
    "email": "E-posta",
    "password": "Şifre",
    "amount": "Tutar",
    "date": "Tarih",
    "name": "Ad",
    "category": "Kategori",
    "account": "Hesap",
    "kind": "Tür",
    "target_amount": "Hedef tutar",
    "start_date": "Başlangıç tarihi",
    "end_date": "Bitiş tarihi",
    "last4": "Son 4 hane",
}


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: str | None = None, data=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.data = data


class SessionExpired(ApiError):
    pass


def _error_message(data) -> str:
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        parts = []
        for key, value in data.items():
            msg = value[0] if isinstance(value, list) and value else value
            if isinstance(msg, dict):
                msg = _error_message(msg)
            parts.append(str(msg) if key == "non_field_errors" else f"{FIELD_LABELS.get(key, key)}: {msg}")
        if parts:
            return "\n".join(parts)
    if isinstance(data, list) and data:
        return str(data[0])
    return "Beklenmeyen bir hata oluştu."


class ApiClient:
    """Async JSON client with JWT auth and single-flight automatic token refresh."""

    def __init__(self, base_url: str, tokens, on_session_expired: Callable[[], Awaitable[None]]):
        self.tokens = tokens
        self._on_session_expired = on_session_expired
        self._http = httpx.AsyncClient(base_url=base_url + "/", timeout=20)
        self._refresh_lock = asyncio.Lock()

    async def get(self, path, params=None):
        return await self.request("GET", path, params=params)

    async def post(self, path, json=None, auth=True):
        return await self.request("POST", path, json=json, auth=auth)

    async def patch(self, path, json=None):
        return await self.request("PATCH", path, json=json)

    async def delete(self, path):
        return await self.request("DELETE", path)

    async def request(self, method, path, *, json=None, params=None, auth=True):
        sent_access = self.tokens.access
        response = await self._send(method, path, json, params, sent_access if auth else None)

        if response.status_code == 401 and auth:
            if not await self._refresh(sent_access):
                await self._expire()
            response = await self._send(method, path, json, params, self.tokens.access)
            if response.status_code == 401:
                await self._expire()

        return self._parse(response)

    async def _send(self, method, path, json, params, access):
        headers = {"Authorization": f"Bearer {access}"} if access else {}
        try:
            return await self._http.request(method, path, json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ApiError(0, NETWORK_ERROR) from exc

    async def _refresh(self, sent_access) -> bool:
        """Refresh once even if many requests fail at the same time (old refresh token is blacklisted after use)."""
        async with self._refresh_lock:
            if self.tokens.access and self.tokens.access != sent_access:
                return True  # another request already refreshed
            if not self.tokens.refresh:
                return False
            response = await self._send("POST", "auth/refresh/", {"refresh": self.tokens.refresh}, None, None)
            if response.status_code != 200:
                return False
            data = response.json()
            await self.tokens.save(data["access"], data.get("refresh"))
            return True

    async def _expire(self):
        await self.tokens.clear()
        await self._on_session_expired()
        raise SessionExpired(401, SESSION_EXPIRED, "session_expired")

    @staticmethod
    def _parse(response: httpx.Response):
        if response.status_code == 204 or not response.content:
            data = None
        else:
            try:
                data = response.json()
            except ValueError:
                data = None
        if response.is_success:
            return data
        code = data.get("code") if isinstance(data, dict) else None
        raise ApiError(response.status_code, _error_message(data), code, data)
