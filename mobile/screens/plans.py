from datetime import date

import flet as ft

from .choices import FREQUENCIES, PLAN_TYPES, label
from .transactions import account_options, category_options
from .ui import (
    DateInput, FormError, dropdown, dropdown_value, empty_text, fmt_date, fmt_money, form_view,
    guarded, money_field, parse_money, text_field, toast,
)


def plan_tile(state, p, on_changed) -> ft.ListTile:
    """Upcoming/plan row. Manual active plans get a quick pay button; tap opens the plan form."""
    if p["plan_type"] == "installment":
        kind_text = f"Taksit {p['paid_count'] + 1}/{p['installment_count']}" if p["is_active"] else \
            f"Taksit {p['paid_count']}/{p['installment_count']}"
    else:
        kind_text = label(FREQUENCIES, p["frequency"])
    status = (f"Vade: {fmt_date(p['next_due_date'])}" + (" (gecikti)" if p["is_overdue"] else "")) \
        if p["is_active"] else "Tamamlandı/Pasif"
    sign = "+" if p["kind"] == "income" else "-"

    if p["is_active"] and not p["auto_pay"]:
        trailing = ft.Row(
            [ft.Text(sign + fmt_money(p["amount"])),
             ft.TextButton("Alındı" if p["kind"] == "income" else "Öde",
                           on_click=lambda e: pay_dialog(state, p, on_changed))],
            tight=True,
        )
    else:
        trailing = ft.Text(sign + fmt_money(p["amount"]) + ("\nOtomatik" if p["auto_pay"] and p["is_active"] else ""))

    return ft.ListTile(
        title=ft.Text(p["description"]),
        subtitle=ft.Text(f"{status} · {kind_text}", color=ft.Colors.RED_700 if p["is_overdue"] else None),
        trailing=trailing,
        on_click=lambda e: state.router.push(plan_form(state, p, on_saved=on_changed)),
    )


def pay_dialog(state, p, on_done):
    page = state.page
    amount = money_field("Tutar", p["amount"])
    day = DateInput(page, "Tarih", date.today())

    async def pay():
        await state.budget.pay_plan(p["id"], amount=parse_money(amount.value), date=day.iso)
        page.pop_dialog()
        toast(page, "Kaydedildi, hareketlere eklendi.")
        await on_done()

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(p["description"]),
            content=ft.Column([amount, day.control], tight=True),
            actions=[
                ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()),
                ft.FilledButton("Kaydet", on_click=guarded(page, pay)),
            ],
        )
    )


def plan_form(state, p: dict, on_saved) -> ft.View:
    """Edit an existing plan. Type, kind, total and installment count are fixed after creation."""
    page = state.page
    is_installment = p["plan_type"] == "installment"

    if is_installment:
        info = (f"Taksitli · Toplam {fmt_money(p['total_amount'])} · "
                f"{p['paid_count']}/{p['installment_count']} ödendi · Taksit {fmt_money(p['amount'])}")
    else:
        info = f"{label(PLAN_TYPES, p['plan_type'])} · {'Gelir' if p['kind'] == 'income' else 'Gider'}"

    description = text_field("Açıklama", p["description"])
    amount = money_field("Tutar", p["amount"])
    category = dropdown(
        "Kategori", category_options(state, p["kind"], p["category"]), p["category"], with_none=True
    )
    account = dropdown("Hesap", account_options(state, p["account"]), p["account"])
    frequency = dropdown("Sıklık", FREQUENCIES, p["frequency"])
    next_due = DateInput(page, "Sonraki vade", p["next_due_date"])
    end = DateInput(page, "Bitiş tarihi (opsiyonel)", p["end_date"], optional=True)
    auto_pay = ft.Switch(label="Vade gününde otomatik öde", value=p["auto_pay"])
    is_active = ft.Switch(label="Aktif", value=p["is_active"])
    note = text_field("Not", p["note"], multiline=True)

    async def save():
        if not description.value:
            raise FormError("Açıklama gerekli.")
        payload = {
            "description": description.value,
            "category": dropdown_value(category),
            "account": account.value,
            "next_due_date": next_due.iso,
            "auto_pay": auto_pay.value,
            "is_active": is_active.value,
            "note": note.value,
        }
        if not is_installment:
            payload.update(amount=parse_money(amount.value), frequency=frequency.value, end_date=end.iso)
        await state.budget.plans.update(p["id"], payload)
        state.router.pop()
        await on_saved()

    async def delete():
        await state.budget.plans.delete(p["id"])
        state.router.pop()
        await on_saved()

    controls = [ft.Text(info, color=ft.Colors.GREY_700), description]
    if not is_installment:
        controls += [amount, frequency]
    controls += [category, account, next_due.control]
    if not is_installment:
        controls += [end.control]
    controls += [auto_pay, is_active, note]

    return form_view(
        state, "/plan", "Ödeme planı", controls, on_save=save, on_delete=delete,
        delete_message="Plan silinecek. Daha önce oluşan hareketler korunur.",
    )


class PlansScreen:
    """All payment plans incl. finished/inactive (More > Payment plans)."""

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True)
        self.view = ft.View(route="/plans", appbar=ft.AppBar(title=ft.Text("Ödeme Planları")), controls=[self.list])
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        plans = (await self.state.budget.plans.list(page_size=100))["results"]
        self.list.controls = [plan_tile(self.state, p, self.refresh) for p in plans] or [empty_text("Ödeme planı yok.")]
        self.page.update()
