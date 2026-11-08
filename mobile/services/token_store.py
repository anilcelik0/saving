class TokenStore:
    """Persists JWT tokens in device key-value storage.

    TODO(security): SharedPreferences is not encrypted; switch to a secure storage
    extension before release.
    """

    ACCESS_KEY = "saving.access"
    REFRESH_KEY = "saving.refresh"

    def __init__(self, prefs):
        self._prefs = prefs
        self.access: str | None = None
        self.refresh: str | None = None

    async def load(self):
        self.access = await self._prefs.get(self.ACCESS_KEY)
        self.refresh = await self._prefs.get(self.REFRESH_KEY)

    async def save(self, access: str, refresh: str | None = None):
        self.access = access
        await self._prefs.set(self.ACCESS_KEY, access)
        if refresh:
            self.refresh = refresh
            await self._prefs.set(self.REFRESH_KEY, refresh)

    async def clear(self):
        self.access = self.refresh = None
        await self._prefs.remove(self.ACCESS_KEY)
        await self._prefs.remove(self.REFRESH_KEY)

    @property
    def has_session(self) -> bool:
        return bool(self.refresh)
