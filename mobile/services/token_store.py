import asyncio
import logging

log = logging.getLogger(__name__)


class TokenStore:
    """
    Persists JWT tokens. Uses encrypted storage (flet-secure-storage: Android Keystore / iOS Keychain) when it is
    available; otherwise (package not installed, desktop `flet run` client without the extension) falls back to
    SharedPreferences and reports `encrypted = False` (shown in Uygulama ayarları).
    Tokens found in SharedPreferences from older versions are moved to secure storage once and removed there.
    """

    ACCESS_KEY = "saving.access"
    REFRESH_KEY = "saving.refresh"
    PROBE_TIMEOUT = 3  # seconds; the call never answers when the client lacks the extension

    def __init__(self, prefs, secure=None):
        self._prefs = prefs
        self._secure = secure
        self._store = prefs
        self.encrypted = False
        self.access: str | None = None
        self.refresh: str | None = None

    async def _secure_works(self) -> bool:
        if self._secure is None:
            return False
        try:
            await asyncio.wait_for(self._secure.contains_key(self.REFRESH_KEY), self.PROBE_TIMEOUT)
            return True
        except Exception as err:  # timeout, missing extension, keystore error
            log.warning("Secure storage unavailable, tokens stay in SharedPreferences: %r", err)
            return False

    async def load(self):
        if await self._secure_works():
            self._store, self.encrypted = self._secure, True
            await self._migrate_from_prefs()
        self.access = await self._store.get(self.ACCESS_KEY)
        self.refresh = await self._store.get(self.REFRESH_KEY)

    async def _migrate_from_prefs(self):
        for key in (self.ACCESS_KEY, self.REFRESH_KEY):
            value = await self._prefs.get(key)
            if value:
                if not await self._secure.get(key):
                    await self._secure.set(key, value)
                await self._prefs.remove(key)

    async def save(self, access: str, refresh: str | None = None):
        self.access = access
        await self._store.set(self.ACCESS_KEY, access)
        if refresh:
            self.refresh = refresh
            await self._store.set(self.REFRESH_KEY, refresh)

    async def clear(self):
        self.access = self.refresh = None
        await self._store.remove(self.ACCESS_KEY)
        await self._store.remove(self.REFRESH_KEY)

    @property
    def has_session(self) -> bool:
        return bool(self.refresh)
