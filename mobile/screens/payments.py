from datetime import date

import flet as ft

from .choices import FREQUENCIES, label
from .transactions import account_options, category_options
from .ui import (
    DateInput, FormError, dropdown, dropdown_value, empty_text, fmt_date, fmt_money, form_view,
    guarded, int_field, money_field, parse_int, parse_money, text_field, toast,
)


class PaymentsTab:
    title = "Düzenli Ödemeler"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.upcoming_only = ft.Switch(label="Sadece yaklaşan 30 gün", value=True)
        self.upcoming_only.on_change = lambda e: self.page.run_task(self.refresh)
        self.list = ft.ListView(expand=True)
        self.control = ft.Column([ft.Container(self.upcoming_only, padding=8), self.list], expand=True)
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda e: self.open_form(None))

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        if self.upcoming_only.value:
            items = await self.state.budget.upcoming_payments(days=30)
        else:
            items = (await self.state.budget.recurring.list(page_size=100))["results"]
        self.list.controls = [self._tile(p) for p in items] or [empty_text("Kayıtlı ödeme yok.")]
        self.page.update()

    def _tile(self, p):
        due = f"Vade: {fmt_date(p['next_due_date'])}" if p["is_active"] else "Pasif"
        parts = [due, label(FREQUENCIES, p["frequency"])]
        if p["installment_count"]:
            parts.append(f"Taksit {p['paid_count']}/{p['installment_count']}")
        return ft.ListTile(
            title=ft.Text(p["name"]),
            subtitle=ft.Text(" · ".join(parts), color=ft.Colors.RED_700 if p["is_overdue"] else None),
            trailing=ft.Text(fmt_money(p["amount"])),
            on_click=lambda e, p=p: self._actions(p),
        )

    def _actions(self, p):
        page = self.page

        def close_then(fn):
            def handler(e):
                page.pop_dialog()
                fn()
            return handler

        actions = [ft.TextButton("Düzenle", on_click=close_then(lambda: self.open_form(p)))]
        if p["is_active"]:
            actions.insert(0, ft.TextButton("Ödendi olarak işaretle", on_click=close_then(lambda: self._pay_dialog(p))))
        page.show_dialog(ft.AlertDialog(title=ft.Text(p["name"]), actions=actions))

    def _pay_dialog(self, p):
        page = self.page
        amount = money_field("Ödenen tutar", p["amount"])
        day = DateInput(page, "Ödeme tarihi", date.today())

        async def pay():
            await self.state.budget.pay_recurring(p["id"], amount=parse_money(amount.value), date=day.iso)
            page.pop_dialog()
            toast(page, "Ödeme kaydedildi, gider olarak eklendi.")
            await self.refresh()

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"{p['name']} ödemesi"),
                content=ft.Column([amount, day.control], tight=True),
                actions=[
                    ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton("Kaydet", on_click=guarded(page, pay)),
                ],
            )
        )

    def open_form(self, payment):
        self.state.router.push(recurring_form(self.state, payment, on_saved=self.refresh))


def recurring_form(state, p: dict | None, on_saved) -> ft.View:
    p = p or {}
    page = state.page
    is_edit = bool(p.get("id"))
    name = text_field("Ad", p.get("name"))
    amount = money_field("Tutar", p.get("amount"))
    frequency = dropdown("Sıklık", FREQUENCIES, p.get("frequency", "monthly"))
    interval = int_field("Her kaç periyotta bir", p.get("interval", 1))
    start = DateInput(page, "Başlangıç tarihi", p.get("start_date") or date.today())
    next_due = DateInput(page, "Sonraki vade", p.get("next_due_date"))
    end = DateInput(page, "Bitiş tarihi (opsiyonel)", p.get("end_date"), optional=True)
    installments = int_field("Taksit sayısı (opsiyonel)", p.get("installment_count"))
    category = dropdown(
        "Kategori", category_options(state, "expense", p.get("category")), p.get("category"), with_none=True
    )
    account = dropdown("Hesap", account_options(state, p.get("account")), p.get("account"), with_none=True)
    is_active = ft.Switch(label="Aktif", value=p.get("is_active", True))
    note = text_field("Not", p.get("note"), multiline=True)

    async def save():
        if not name.value:
            raise FormError("Ad gerekli.")
        payload = {
            "name": name.value,
            "amount": parse_money(amount.value),
            "frequency": frequency.value,
            "interval": parse_int(interval, "Tekrar aralığı", required=True),
            "start_date": start.iso,
            "end_date": end.iso,
            "installment_count": parse_int(installments, "Taksit sayısı"),
            "category": dropdown_value(category),
            "account": dropdown_value(account),
            "note": note.value,
        }
        if is_edit:
            payload.update(next_due_date=next_due.iso, is_active=is_active.value)
            await state.budget.recurring.update(p["id"], payload)
        else:
            await state.budget.recurring.create(payload)
        state.router.pop()
        await on_saved()

    async def delete():
        await state.budget.recurring.delete(p["id"])
        state.router.pop()
        await on_saved()

    controls = [name, amount, frequency, interval, start.control]
    if is_edit:
        controls += [next_due.control]
    controls += [end.control, installments, category, account]
    if is_edit:
        controls += [is_active]
    controls += [note]

    return form_view(
        state, "/recurring", "Ödemeyi düzenle" if is_edit else "Yeni düzenli ödeme", controls,
        on_save=save, on_delete=delete if is_edit else None,
        delete_message="Ödeme planı silinecek. Daha önce oluşan işlemler korunur.",
    )
