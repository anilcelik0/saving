from datetime import date

import flet as ft

from .choices import MONTHS
from .transactions import open_entry_form, transaction_tile
from .ui import confirm, empty_text, fmt_date, fmt_money, guarded, toast

CYCLE_STATUS = {"paid": "Ödendi", "pending": "Ödenmedi", "partial": "Kısmen ödendi", "cancelled": "İptal"}


def item_tile(state, item, on_changed) -> ft.Control:
    """Activity row: a single transaction, or a card statement cycle grouped per account."""
    if item["type"] == "transaction":
        return transaction_tile(state, item["transaction"], on_changed)
    return cycle_tile(state, item, on_changed)


def cycle_tile(state, c, on_changed) -> ft.ListTile:
    day = f" (kesim {c['statement_day']})" if c["statement_day"] else ""
    status = CYCLE_STATUS.get(c["status"], c["status"])
    if c["status"] == "partial":
        status += f" · kalan {fmt_money(c['pending_amount'])}"
    parts = [f"{fmt_date(c['start'])} – {fmt_date(c['end'])}", f"{c['count']} işlem", status]
    if not c["in_balance"]:
        parts.append("bakiyeye dahil değil")
    color = ft.Colors.RED_700 if c["status"] in ("pending", "partial") else None
    return ft.ListTile(
        leading=ft.Icon(ft.Icons.CREDIT_CARD),
        title=ft.Text(f"{c['card_name']} · Ekstre {fmt_date(c['end'])}{day}"),
        subtitle=ft.Text(" · ".join(parts), color=color),
        trailing=ft.Text(("-" if c["net"].startswith("-") else "+") + fmt_money(c["net"].lstrip("-")),
                         color=ft.Colors.RED_700 if c["net"].startswith("-") else ft.Colors.GREEN_700),
        on_click=lambda e: state.router.push(CardCycleView(state, c, on_changed).view),
    )


class ActivityTab:
    """
    Month view of money movements (same scope as the monthly summary): card transactions grouped into one
    row per account statement cycle, other movements one by one (incl. this month's pending ones with a
    quick pay button). Navigation: any past month, at most one month ahead.
    """

    title = "Hareketler"
    MAX_MONTHS_AHEAD = 1

    def __init__(self, state):
        self.state = state
        self.page = state.page
        today = date.today()
        self.year, self.month = today.year, today.month
        self.max_index = today.year * 12 + today.month - 1 + self.MAX_MONTHS_AHEAD
        self.history = ft.Column(spacing=0)
        self.month_label = ft.Text(weight=ft.FontWeight.BOLD)
        self.next_button = ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=lambda e: self._shift(1))
        self.control = ft.ListView(
            [
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=lambda e: self._shift(-1)),
                        self.month_label,
                        self.next_button,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                self.history,
            ],
            expand=True,
        )
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda e: open_entry_form(state, None, self.refresh))

    def _index(self):
        return self.year * 12 + self.month - 1

    def _shift(self, delta):
        index = min(self._index() + delta, self.max_index)
        self.year, self.month = index // 12, index % 12 + 1
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        self.month_label.value = f"{MONTHS[self.month - 1]} {self.year}"
        self.next_button.disabled = self._index() >= self.max_index
        items = await self.state.budget.activity(f"{self.year:04d}-{self.month:02d}")
        self.history.controls = [item_tile(self.state, i, self.refresh) for i in items] or \
            [empty_text("Bu ay hareket yok.")]
        self.page.update()


class CardCycleView:
    """One card statement cycle of an account: its transactions + mark all paid / unpaid."""

    def __init__(self, state, cycle, on_changed):
        self.state = state
        self.page = state.page
        self.cycle = cycle
        self.on_changed = on_changed
        self.header = ft.Text()
        self.list = ft.ListView(expand=True)
        self.view = ft.View(
            route="/card-cycle",
            appbar=ft.AppBar(title=ft.Text(f"{cycle['card_name']} · {fmt_date(cycle['end'])}")),
            controls=[
                ft.Container(self.header, padding=ft.Padding.symmetric(horizontal=16)),
                ft.Row(
                    [
                        ft.FilledButton("Tümünü ödendi işaretle",
                                        on_click=lambda e: self._bulk("paid", "Bu dönemin tüm harcamaları ödendi sayılacak.")),
                        ft.OutlinedButton("Tümünü ödenmedi yap",
                                          on_click=lambda e: self._bulk("pending", "Bu dönemin tüm harcamaları ödenmedi olarak işaretlenecek.")),
                    ],
                    wrap=True,
                ),
                self.list,
            ],
            padding=8,
        )
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        c = self.cycle
        data = await self.state.budget.transactions.list(
            account=c["account"], cycle_start=c["start"], cycle_end=c["end"], ordering="date", page_size=100,
        )
        rows = data["results"]
        active = [t for t in rows if t["status"] != "cancelled"]
        expense = sum(float(t["amount"]) for t in active if t["kind"] == "expense")
        income = sum(float(t["amount"]) for t in active if t["kind"] == "income")
        unpaid = sum(1 for t in active if t["status"] == "pending")
        self.header.value = (
            f"Dönem: {fmt_date(c['start'])} – {fmt_date(c['end'])}\n"
            f"Ekstre toplamı: {fmt_money(expense - income)} · {len(rows)} işlem"
            + (f" · {unpaid} ödenmemiş" if unpaid else " · tamamı ödendi")
        )
        self.list.controls = [transaction_tile(self.state, t, self._changed) for t in rows] or [empty_text("İşlem yok.")]
        self.page.update()

    async def _changed(self):
        await self.refresh()
        await self.on_changed()

    def _bulk(self, status, message):
        async def run():
            c = self.cycle
            result = await self.state.budget.transactions.bulk_status(c["account"], c["start"], c["end"], status)
            toast(self.page, f"{result['updated']} işlem güncellendi.")
            await self._changed()

        confirm(self.page, message, run)
