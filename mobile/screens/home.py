import flet as ft

from .activity import ActivityTab
from .invest import InvestTab
from .more import MoreTab
from .summary import SummaryTab
from .theme import ACCENT, MUTED, icon_badge, muted
from .ui import guarded, toast

TILE_HEIGHT = 136

NAV = [
    (ft.Icons.DASHBOARD_OUTLINED, ft.Icons.DASHBOARD, "Özet"),
    (ft.Icons.RECEIPT_LONG_OUTLINED, ft.Icons.RECEIPT_LONG, "Hareketler"),
    (ft.Icons.SHOW_CHART, ft.Icons.SHOW_CHART, "Yatırımlar"),
    (ft.Icons.MORE_HORIZ, ft.Icons.MORE_HORIZ, "Diğer"),
]


class HomeScreen:
    """Shell: large title, current tab, bottom bar (4 tabs) with a central + button opening the add menu."""

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.tabs = [SummaryTab(state), ActivityTab(state), InvestTab(state), MoreTab(state)]
        self.index = 0
        self.picker = ft.FilePicker()
        self.title = ft.Text(size=26, weight=ft.FontWeight.W_700)
        self.body = ft.Container(expand=True)
        self.nav_items = [self._nav_item(i) for i in range(len(NAV))]
        self.view = ft.View(
            route="/",
            controls=[ft.SafeArea(ft.Column([
                ft.Container(ft.Row([
                    ft.Container(self.title, expand=True),
                    # testing phase: a problem can be reported from every tab
                    ft.IconButton(ft.Icons.BUG_REPORT_OUTLINED, tooltip="Sorun bildir", icon_color=MUTED,
                                  on_click=lambda e: state.open_report()),
                ]), padding=ft.Padding.only(left=20, right=8, top=12, bottom=4)),
                self.body,
            ], spacing=0, expand=True), expand=True)],
            padding=0,
            bgcolor=ft.Colors.SURFACE,
            floating_action_button=ft.FloatingActionButton(
                icon=ft.Icons.ADD, bgcolor=ft.Colors.PRIMARY, foreground_color=ft.Colors.ON_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=18), tooltip="Ekle", on_click=lambda e: self.open_add_menu()),
            floating_action_button_location=ft.FloatingActionButtonLocation.CENTER_DOCKED,
            navigation_bar=ft.BottomAppBar(
                content=ft.Row([*self.nav_items[:2], ft.Container(width=64), *self.nav_items[2:]], spacing=0),
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST, padding=ft.Padding.symmetric(horizontal=4), height=72,
            ),
        )
        self.select(state.settings.start_tab if state.settings else 0, update=False)

    def _nav_item(self, index):
        icon, _, label = NAV[index]
        return ft.Container(
            ft.Column([ft.Icon(icon, size=24), ft.Text(label, size=11)], spacing=2, tight=True,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, alignment=ft.Alignment.CENTER, border_radius=14, ink=True,
            on_click=lambda e: self.select(index),
        )

    def _paint_nav(self):
        for i, item in enumerate(self.nav_items):
            selected = i == self.index
            icon, text = item.content.controls
            icon.icon = NAV[i][1] if selected else NAV[i][0]
            icon.color = text.color = ACCENT if selected else MUTED
            text.weight = ft.FontWeight.W_600 if selected else None

    def select(self, index: int, update=True):
        self.index = index
        tab = self.tabs[index]
        self.title.value = tab.title
        self.body.content = tab.control
        self._paint_nav()
        if update:
            self.page.update()
        self.page.run_task(tab.refresh)

    async def refresh_current(self):
        await self.tabs[self.index].refresh()

    # ---------------------------------------------------------------- + menu
    def open_add_menu(self):
        state, page = self.state, self.page
        done = self.refresh_current

        def run(action):
            def handler(e):
                page.pop_dialog()
                action()
            return handler

        def entry():
            from .transactions import open_entry_form
            open_entry_form(state, None, done)

        def statement():
            from .statements import upload_dialog
            upload_dialog(state, self.picker, done)

        async def asset():
            from .invest import trade_form
            assets = await state.invest.assets()
            if not assets:
                toast(page, "Varlık listesi yüklenemedi.", error=True)
                return
            state.router.push(trade_form(state, assets, None, "buy", None, done))

        def deposit():
            from .invest import deposit_form
            state.router.push(deposit_form(state, None, done))

        def account():
            from .more import account_form

            async def saved():
                await state.load_refs()
                await done()
            state.router.push(account_form(state, None, saved))

        def tile(icon, color, title, subtitle, action):
            return ft.Container(
                ft.Column([icon_badge(icon, color), ft.Text(title, size=15, weight=ft.FontWeight.W_600),
                           muted(subtitle)], spacing=8),
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOW, border_radius=20, padding=16, expand=True, ink=True,
                height=TILE_HEIGHT, on_click=run(action),
            )

        # Fixed tile heights: a bottom sheet sizes itself to its content, so nothing inside may "fill" vertically
        # (stretch/expand in the vertical direction makes the height unbounded and the sheet fails to lay out).
        sheet = ft.BottomSheet(
            ft.Container(ft.Column([
                ft.Row([ft.Text("Ne eklemek istersiniz?", size=18, weight=ft.FontWeight.W_700, expand=True),
                        ft.IconButton(ft.Icons.CLOSE, tooltip="Kapat", on_click=lambda e: page.pop_dialog())]),
                ft.Row([
                    tile(ft.Icons.SWAP_VERT, "#0F766E", "Gelir / gider", "Tek seferlik, düzenli, taksitli", entry),
                    tile(ft.Icons.UPLOAD_FILE, "#1D4ED8", "Ekstre yükle", "PDF / Excel, önizleyip aktar", statement),
                ], spacing=12),
                ft.Row([
                    tile(ft.Icons.SAVINGS, "#B45309", "Altın / döviz", "Alış ekle", lambda: page.run_task(guarded(page, asset))),
                    tile(ft.Icons.ACCOUNT_BALANCE, "#6D28D9", "Vadeli mevduat", "Faiz, vade, vade sonu", deposit),
                ], spacing=12),
                ft.ListTile(leading=ft.Icon(ft.Icons.ADD_CARD), title=ft.Text("Hesap ekle"),
                            trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT), on_click=run(account)),
            ], spacing=12, tight=True, scroll=ft.ScrollMode.AUTO),
                padding=ft.Padding.only(left=20, right=20, top=4, bottom=24)),
            show_drag_handle=True, scrollable=True, bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
            shape=ft.RoundedRectangleBorder(radius=28),
        )
        page.show_dialog(sheet)
