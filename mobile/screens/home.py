import flet as ft

from .goals import GoalsTab
from .more import MoreTab
from .payments import PaymentsTab
from .transactions import TransactionsTab


class HomeScreen:
    """Bottom-navigation shell. Each tab exposes: title, control, fab (or None), async refresh()."""

    def __init__(self, state):
        self.state = state
        self.tabs = [TransactionsTab(state), PaymentsTab(state), GoalsTab(state), MoreTab(state)]
        self.title = ft.Text()
        self.body = ft.Container(expand=True)
        self.view = ft.View(
            route="/",
            appbar=ft.AppBar(title=self.title),
            navigation_bar=ft.NavigationBar(
                destinations=[
                    ft.NavigationBarDestination(icon=ft.Icons.RECEIPT_LONG, label="İşlemler"),
                    ft.NavigationBarDestination(icon=ft.Icons.EVENT_REPEAT, label="Ödemeler"),
                    ft.NavigationBarDestination(icon=ft.Icons.SAVINGS, label="Hedefler"),
                    ft.NavigationBarDestination(icon=ft.Icons.MENU, label="Diğer"),
                ],
                on_change=lambda e: self.select(e.control.selected_index),
            ),
            controls=[self.body],
            padding=0,
        )
        self.select(0, update=False)

    def select(self, index: int, update=True):
        tab = self.tabs[index]
        self.title.value = tab.title
        self.body.content = tab.control
        self.view.floating_action_button = tab.fab
        if update:
            self.state.page.update()
        self.state.page.run_task(tab.refresh)
