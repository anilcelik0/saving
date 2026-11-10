class SettingsStore:
    """Device-level app preferences (theme, defaults). Kept on the phone, not on the server."""

    PREFIX = "saving.settings."
    DEFAULTS = {
        "theme": "system",  # system | light | dark
        "default_account": "",  # account id preselected in new entry forms ("" = first account)
        "upcoming_days": "30",  # home: upcoming payments window
        "start_tab": "0",  # 0 Özet, 1 Hareketler, 2 Yatırımlar
        "hide_amounts": "false",  # home: mask balances (e.g. when others can see the screen)
    }

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
