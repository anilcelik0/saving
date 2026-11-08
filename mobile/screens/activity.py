import asyncio

import flet as ft

from .choices import KINDS
from .plans import plan_tile
from .transactions import open_entry_form, transaction_tile
from .ui import dropdown, empty_text, guarded

ALL = "all"
UPCOMING_DAYS = 30


class ActivityTab:
    """
    Single money-movement page:
      - Upcoming: plan occurrences due within 30 days (incl. overdue), quick pay for manual ones
      - History: realized transactions (kind filter, load more)
    One "+" opens the unified entry form (one-time / recurring / installment).
    """

    title = "Hareketler"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.items: list = []
        self.page_no = 1
        self.has_next = False

        self.kind = dropdown("Tür", [(ALL, "Tümü"), *KINDS], ALL)
        self.kind.on_select = lambda e: self.page.run_task(self.refresh)
        self.upcoming = ft.Column(spacing=0)
        self.history = ft.Column(spacing=0)
        self.more_button = ft.TextButton("Daha fazla yükle", on_click=guarded(self.page, self._load_more))
        self.control = ft.ListView(
            [
                self._header(f"Yaklaşan ({UPCOMING_DAYS} gün)"),
                self.upcoming,
                self._header("Geçmiş"),
                ft.Container(self.kind, padding=ft.Padding.symmetric(horizontal=16)),
                self.history,
            ],
            expand=True,
        )
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda e: open_entry_form(state, None, self.refresh))

    @staticmethod
    def _header(text):
        return ft.Container(ft.Text(text, weight=ft.FontWeight.BOLD), padding=ft.Padding.only(left=16, top=16, bottom=4))

    async def refresh(self):
        self.page_no, self.items = 1, []
        await guarded(self.page, self._fetch_all)()

    async def _fetch_all(self):
        upcoming, _ = await asyncio.gather(self.state.budget.upcoming_plans(days=UPCOMING_DAYS), self._fetch_history())
        self.upcoming.controls = [plan_tile(self.state, p, self.refresh) for p in upcoming] or \
            [empty_text("Yaklaşan ödeme yok.")]
        self._render_history()

    async def _load_more(self):
        self.page_no += 1
        await self._fetch_history()
        self._render_history()

    async def _fetch_history(self):
        kind = None if self.kind.value == ALL else self.kind.value
        data = await self.state.budget.transactions.list(page=self.page_no, kind=kind)
        self.items += data["results"]
        self.has_next = bool(data["next"])

    def _render_history(self):
        controls = [transaction_tile(self.state, t, self.refresh) for t in self.items] or \
            [empty_text("Henüz hareket yok.")]
        if self.has_next:
            controls.append(self.more_button)
        self.history.controls = controls
        self.page.update()
