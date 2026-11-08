from datetime import date

import flet as ft

from .choices import KINDS, NONE
from .ui import (
    DateInput, dropdown, dropdown_value, empty_text, fmt_date, fmt_money,
    form_view, guarded, money_field, parse_money, text_field,
)

ALL = "all"


class TransactionsTab:
    title = "İşlemler"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.items: list = []
        self.page_no = 1
        self.has_next = False

        self.kind = dropdown("Tür", [(ALL, "Tümü"), *KINDS], ALL)
        self.kind.on_select = lambda e: self.page.run_task(self.refresh)
        self.list = ft.ListView(expand=True)
        self.more_button = ft.TextButton("Daha fazla yükle", on_click=guarded(self.page, self._load_more))
        self.control = ft.Column([ft.Container(self.kind, padding=8), self.list], expand=True)
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda e: self.open_form(None))

    async def refresh(self):
        self.page_no, self.items = 1, []
        await guarded(self.page, self._fetch)()

    async def _load_more(self):
        self.page_no += 1
        await self._fetch()

    async def _fetch(self):
        kind = None if self.kind.value == ALL else self.kind.value
        data = await self.state.budget.transactions.list(page=self.page_no, kind=kind)
        self.items += data["results"]
        self.has_next = bool(data["next"])
        self._render()

    def _render(self):
        controls = [self._tile(t) for t in self.items] or [empty_text("Henüz işlem yok.")]
        if self.has_next:
            controls.append(self.more_button)
        self.list.controls = controls
        self.page.update()

    def _tile(self, t):
        is_expense = t["kind"] == "expense"
        details = [fmt_date(t["date"]), self.state.category_name(t["category"])]
        if t["account"]:
            details.append(self.state.account_name(t["account"]))
        return ft.ListTile(
            title=ft.Text(t["description"] or self.state.category_name(t["category"])),
            subtitle=ft.Text(" · ".join(details)),
            trailing=ft.Text(
                ("-" if is_expense else "+") + fmt_money(t["amount"]),
                color=ft.Colors.RED_700 if is_expense else ft.Colors.GREEN_700,
            ),
            on_click=lambda e, t=t: self.open_form(t),
        )

    def open_form(self, txn):
        self.state.router.push(transaction_form(self.state, txn, on_saved=self.refresh))


def category_options(state, kind, current=None):
    return [
        (c["id"], c["name"])
        for c in state.categories
        if c["kind"] == kind and (not c["is_archived"] or c["id"] == current)
    ]


def account_options(state, current=None):
    return [(a["id"], a["name"]) for a in state.accounts if not a["is_archived"] or a["id"] == current]


def transaction_form(state, txn: dict | None, on_saved) -> ft.View:
    txn = txn or {}
    page = state.page
    kind = dropdown("Tür", KINDS, txn.get("kind", "expense"))
    amount = money_field("Tutar", txn.get("amount"))
    day = DateInput(page, "Tarih", txn.get("date") or date.today())
    description = text_field("Açıklama", txn.get("description"))
    category = dropdown(
        "Kategori", category_options(state, kind.value, txn.get("category")), txn.get("category"), with_none=True
    )
    account = dropdown("Hesap", account_options(state, txn.get("account")), txn.get("account"), with_none=True)
    note = text_field("Not", txn.get("note"), multiline=True)

    def kind_changed(e):
        options = [(NONE, "Seçilmedi"), *category_options(state, kind.value)]
        category.options = [ft.DropdownOption(key=k, text=t) for k, t in options]
        category.value = NONE
        page.update()

    kind.on_select = kind_changed

    async def save():
        payload = {
            "kind": kind.value,
            "amount": parse_money(amount.value),
            "date": day.iso,
            "description": description.value,
            "category": dropdown_value(category),
            "account": dropdown_value(account),
            "note": note.value,
        }
        if txn.get("id"):
            await state.budget.transactions.update(txn["id"], payload)
        else:
            await state.budget.transactions.create(payload)
        state.router.pop()
        await on_saved()

    async def delete():
        await state.budget.transactions.delete(txn["id"])
        state.router.pop()
        await on_saved()

    return form_view(
        state,
        "/transaction",
        "İşlemi düzenle" if txn.get("id") else "Yeni işlem",
        [kind, amount, day.control, description, category, account, note],
        on_save=save,
        on_delete=delete if txn.get("id") else None,
    )
