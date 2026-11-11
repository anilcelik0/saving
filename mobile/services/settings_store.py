class SettingsStore:
    """Device-level app preferences (theme, defaults). Kept on the phone, not on the server."""

    PREFIX = "saving.settings."
    DEFAULTS = {
        "theme": "system",  # system | light | dark
        "default_account": "",  # account id preselected in new entry forms ("" = first account)
        "upcoming_days": "30",  # home: upcoming payments window
        "start_tab": "0",  # 0 Özet, 1 Hareketler, 2 Yatırımlar
        "hide_amounts": "false",  # home: mask balances (e.g. when others can see the screen)
        "recent_categories": "",  # comma separated ids, most recent first (entry form shows them first)
        "onboarded": "",  # comma separated user ids that have seen the app tour on this device
    }
    RECENT_LIMIT = 8

    def __init__(self, prefs):
        self._prefs = prefs
        self.values = dict(self.DEFAULTS)

    async def load(self):
        for key in self.DEFAULTS:
            value = await self._prefs.get(self.PREFIX + key)
            if value is not None:
                self.values[key] = str(value)

    async def set(self, key: str, value):
        self.values[key] = "" if value is None else str(value)
        await self._prefs.set(self.PREFIX + key, self.values[key])

    # typed accessors
    @property
    def theme(self) -> str:
        return self.values["theme"]

    @property
    def default_account(self) -> str | None:
        return self.values["default_account"] or None

    @property
    def upcoming_days(self) -> int:
        return int(self.values["upcoming_days"] or 30)

    @property
    def start_tab(self) -> int:
        return int(self.values["start_tab"] or 0)

    @property
    def hide_amounts(self) -> bool:
        return self.values["hide_amounts"] == "true"

    @property
    def recent_categories(self) -> list[str]:
        return [x for x in self.values["recent_categories"].split(",") if x]

    def is_onboarded(self, user_key: str) -> bool:
        return user_key in self.values["onboarded"].split(",")

    async def mark_onboarded(self, user_key: str):
        if user_key and not self.is_onboarded(user_key):
            await self.set("onboarded", ",".join(filter(None, [self.values["onboarded"], user_key])))

    async def remember_category(self, category_id):
        if not category_id:
            return
        ids = [category_id] + [x for x in self.recent_categories if x != category_id]
        await self.set("recent_categories", ",".join(ids[: self.RECENT_LIMIT]))
