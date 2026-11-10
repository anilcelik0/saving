"""Diğer > Uygulama ayarları: device preferences, saved and applied immediately."""

import flet as ft

from config import api_base_url

from .theme import THEME_MODES, card, muted, section
from .transactions import account_options
from .ui import dropdown, dropdown_value, guarded, toast

THEMES = [("system", "Telefona uy"), ("light", "Açık"), ("dark", "Koyu")]
UPCOMING = [("7", "7 gün"), ("14", "14 gün"), ("30", "30 gün"), ("60", "60 gün")]
START_TABS = [("0", "Özet"), ("1", "Hareketler"), ("2", "Yatırımlar")]
APP_VERSION = "0.1.0"


def settings_view(state, on_changed) -> ft.View:
    page, settings = state.page, state.settings

    def saver(key, after=None):
        async def save(e):
            value = dropdown_value(e.control) if isinstance(e.control, ft.Dropdown) else e.control.value
            if isinstance(value, bool):
                value = "true" if value else "false"
            await settings.set(key, value)
            if after:
                after(value)
            page.update()
            toast(page, "Kaydedildi.")
            await on_changed()
        return lambda e: page.run_task(guarded(page, lambda: save(e)))

    def apply_theme_mode(value):
        page.theme_mode = THEME_MODES.get(value, ft.ThemeMode.SYSTEM)

    theme = dropdown("Tema", THEMES, settings.theme)
    theme.on_select = saver("theme", apply_theme_mode)
    account = dropdown("Varsayılan hesap", account_options(state), settings.default_account, with_none=True,
                       none_text="İlk hesap")
    account.on_select = saver("default_account")
    upcoming = dropdown("Yaklaşan ödemeler", UPCOMING, str(settings.upcoming_days))
    upcoming.on_select = saver("upcoming_days")
    start_tab = dropdown("Açılış ekranı", START_TABS, str(settings.start_tab))
    start_tab.on_select = saver("start_tab")
    hide = ft.Switch(label="Özet'te tutarları gizle", value=settings.hide_amounts)
    hide.on_change = saver("hide_amounts")

    return ft.View(
        route="/settings",
        appbar=ft.AppBar(title=ft.Text("Uygulama ayarları")),
        controls=[ft.ListView([
            section("Görünüm"),
            card(ft.Column([theme, muted("Telefona uy: telefon koyu moddaysa uygulama da koyu açılır.")], spacing=8)),
            section("Kayıtlar"),
            card(ft.Column([
                account, muted("Yeni gelir/gider formunda bu hesap seçili gelir."),
                upcoming, muted("Özet'teki yaklaşan ödemeler bu kadar gün ileriye bakar."),
            ], spacing=8)),
            section("Açılış ve gizlilik"),
            card(ft.Column([
                start_tab, muted("Uygulama bu sekmeyle açılır."),
                hide, muted("Başkalarının ekranı görebildiği yerlerde bakiye ve tutarlar •••• görünür. "
                            "Özet'teki göz simgesiyle de açılıp kapatılabilir."),
            ], spacing=8)),
            section("Hakkında"),
            card(ft.Column([
                ft.Row([ft.Text("Sürüm", expand=True), muted(APP_VERSION, size=14)]),
                ft.Row([ft.Text("Sunucu", expand=True), muted(api_base_url(page.platform), size=13)]),
                muted("Ayarlar bu cihazda saklanır; çıkış yapınca silinmez."),
            ], spacing=10)),
        ], expand=True, padding=16, spacing=12)],
        padding=0,
    )
