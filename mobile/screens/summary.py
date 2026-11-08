from datetime import date

import flet as ft

from .choices import ACCOUNT_TYPES, MONTHS, label
from .ui import empty_text, fmt_money, guarded


class SummaryTab:
    """Total remaining money, month totals and month-end projection (all computed by the backend)."""

    title = "Özet"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        today = date.today()
        self.year, self.month = today.year, today.month
        self.fab = None
        self.month_label = ft.Text(weight=ft.FontWeight.BOLD)
        self.body = ft.Column(spacing=8)
        self.control = ft.ListView(
            [
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=lambda e: self._shift(-1)),
                        self.month_label,
                        ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=lambda e: self._shift(1)),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                self.body,
            ],
            expand=True,
            padding=16,
        )

    def _shift(self, delta):
        index = self.year * 12 + self.month - 1 + delta
        self.year, self.month = index // 12, index % 12 + 1
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        self.month_label.value = f"{MONTHS[self.month - 1]} {self.year}"
        s = await self.state.budget.summary(f"{self.year:04d}-{self.month:02d}")
        today = date.today()
        is_current_or_future = (self.year, self.month) >= (today.year, today.month)

        rows = [
            self._line("Gelir", s["income"]),
            self._line("Gider", s["expense"]),
            self._line("Bu ay artan", s["net"], bold=True),
            ft.Divider(),
            ft.Text("Hesaplar", weight=ft.FontWeight.BOLD),
        ]
        if s["accounts"]:
            rows += [self._line(f"{a['name']} ({label(ACCOUNT_TYPES, a['account_type'])})", a["balance"]) for a in s["accounts"]]
        else:
            rows.append(empty_text("Henüz hesap yok. Diğer > Hesaplar'dan açılış bakiyesiyle ekleyin."))
        rows.append(self._line("Toplam kalan para", s["total_balance"], bold=True))

        if is_current_or_future:
            rows += [
                ft.Divider(),
                ft.Text("Ay sonuna kadar bekleyen planlar", weight=ft.FontWeight.BOLD),
                self._line("Bekleyen gider", s["planned_expense"]),
                self._line("Bekleyen gelir", s["planned_income"]),
                self._line("Ay sonu tahmini bakiye", s["projected_balance"], bold=True),
            ]
        self.body.controls = rows
        self.page.update()

    @staticmethod
    def _line(text, value, bold=False):
        weight = ft.FontWeight.BOLD if bold else None
        return ft.Row(
            [ft.Text(text, weight=weight, expand=True), ft.Text(fmt_money(value), weight=weight)],
        )
