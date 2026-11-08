from datetime import date
from decimal import Decimal

import flet as ft

from .choices import ACCOUNT_TYPES, MONTHS, label
from .ui import empty_text, fmt_money, guarded


class SummaryTab:
    """Month totals (each month on its own), current balances and month-end projection."""

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

        rows = [
            self._line("Gelir", s["income"], bold=True),
            self._detail(f"alınan {fmt_money(s['income_paid'])} · bekleyen {fmt_money(s['income_pending'])}"),
            self._line("Gider", s["expense"], bold=True),
            self._detail(f"ödenen {fmt_money(s['expense_paid'])} · bekleyen {fmt_money(s['expense_pending'])}"),
            self._line("Ay net", s["net"], bold=True),
            ft.Divider(),
            ft.Text("Hesaplar (şu an)", weight=ft.FontWeight.BOLD),
        ]
        if s["accounts"]:
            rows += [self._line(f"{a['name']} ({label(ACCOUNT_TYPES, a['account_type'])})", a["balance"]) for a in s["accounts"]]
        else:
            rows.append(empty_text("Henüz hesap yok. Diğer > Hesaplar'dan açılış bakiyesiyle ekleyin."))
        rows.append(self._line("Şu anki bakiye", s["current_balance"], bold=True))

        if Decimal(s["overdue_expense"]) or Decimal(s["overdue_income"]):
            rows.append(self._detail(
                f"Geciken: gider {fmt_money(s['overdue_expense'])} · gelir {fmt_money(s['overdue_income'])}",
                color=ft.Colors.RED_700,
            ))
        if s["projected_balance"] is not None:
            rows.append(self._line("Ay sonu tahmini bakiye", s["projected_balance"], bold=True))

        self.body.controls = rows
        self.page.update()

    @staticmethod
    def _line(text, value, bold=False):
        weight = ft.FontWeight.BOLD if bold else None
        return ft.Row([ft.Text(text, weight=weight, expand=True), ft.Text(fmt_money(value), weight=weight)])

    @staticmethod
    def _detail(text, color=None):
        return ft.Text(text, size=12, color=color or ft.Colors.GREY_700)
