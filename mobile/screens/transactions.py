from datetime import date

import flet as ft

from .choices import FREQUENCIES, KINDS, NONE, REPEATS
from .ui import (
    DateInput, FormError, dropdown, dropdown_value, fmt_date, fmt_money,
    form_view, int_field, money_field, parse_int, parse_money, text_field, toast,
)


def transaction_tile(state, t, on_saved) -> ft.ListTile:
    is_expense = t["kind"] == "expense"
    title = t["description"] or state.category_name(t["category"])
    if t["plan_info"]:
        title += f" ({t['plan_info']['label']})"
    details = [fmt_date(t["date"]), state.category_name(t["category"]), state.account_name(t["account"])]
    return ft.ListTile(
        title=ft.Text(title),
        subtitle=ft.Text(" · ".join(filter(None, details))),
        trailing=ft.Text(
            ("-" if is_expense else "+") + fmt_money(t["amount"]),
            color=ft.Colors.RED_700 if is_expense else ft.Colors.GREEN_700,
        ),
        on_click=lambda e: open_entry_form(state, t, on_saved),
    )


def category_options(state, kind, current=None):
    return [
        (c["id"], c["name"])
        for c in state.categories
        if c["kind"] == kind and (not c["is_archived"] or c["id"] == current)
    ]


def account_options(state, current=None):
    return [(a["id"], a["name"]) for a in state.accounts if not a["is_archived"] or a["id"] == current]


def set_category_options(category: ft.Dropdown, state, kind):
    options = [(NONE, "Seçilmedi"), *category_options(state, kind)]
    category.options = [ft.DropdownOption(key=k, text=t) for k, t in options]
    category.value = NONE


def open_entry_form(state, txn, on_saved, repeat="none"):
    if not account_options(state, txn and txn.get("account")):
        toast(state.page, "Önce Diğer > Hesaplar bölümünden bir hesap ekleyin.", error=True)
        return
    state.router.push(entry_form(state, txn, on_saved, repeat))


def entry_form(state, txn: dict | None, on_saved, repeat="none") -> ft.View:
    """
    Single entry point for money movements.
    New entry: one-time -> transaction; recurring/installment -> payment plan (backend splits installments).
    Existing transaction: plain edit.
    """
    txn = txn or {}
    page = state.page
    is_edit = bool(txn.get("id"))
    accounts = account_options(state, txn.get("account"))

    kind = dropdown("Tür", KINDS, txn.get("kind", "expense"))
    repeat_dd = dropdown("Tekrar", REPEATS, repeat)
    amount = money_field("Tutar", txn.get("amount"))
    day = DateInput(page, "Tarih", txn.get("date") or date.today())
    description = text_field("Açıklama", txn.get("description"))
    category = dropdown(
        "Kategori", category_options(state, kind.value, txn.get("category")), txn.get("category"), with_none=True
    )
    account = dropdown("Hesap", accounts, txn.get("account") or accounts[0][0])
    frequency = dropdown("Sıklık", FREQUENCIES, "monthly")
    end = DateInput(page, "Bitiş tarihi (opsiyonel)", optional=True)
    installments = int_field("Taksit sayısı")
    auto_pay = ft.Switch(label="Vade gününde otomatik öde (işlem kendiliğinden oluşsun)", value=False)
    note = text_field("Not", txn.get("note"), multiline=True)

    def refresh_visibility():
        mode = repeat_dd.value
        amount.label = "Toplam tutar" if mode == "installment" else "Tutar"
        day.text.label = "Tarih" if mode == "none" else "İlk ödeme tarihi"
        frequency.visible = end.control.visible = mode == "recurring"
        installments.visible = mode == "installment"
        auto_pay.visible = mode != "none"

    def kind_changed(e):
        set_category_options(category, state, kind.value)
        page.update()

    def repeat_changed(e):
        refresh_visibility()
        page.update()

    kind.on_select = kind_changed
    repeat_dd.on_select = repeat_changed
    refresh_visibility()

    async def save():
        common = {
            "kind": kind.value,
            "description": description.value,
            "category": dropdown_value(category),
            "account": account.value,
            "note": note.value,
        }
        mode = repeat_dd.value
        if is_edit or mode == "none":
            payload = {**common, "amount": parse_money(amount.value), "date": day.iso}
            if is_edit:
                await state.budget.transactions.update(txn["id"], payload)
            else:
                await state.budget.transactions.create(payload)
        else:
            if not description.value:
                raise FormError("Düzenli/taksitli işlemler için açıklama gerekli.")
            payload = {**common, "plan_type": mode, "start_date": day.iso, "auto_pay": auto_pay.value}
            if mode == "installment":
                payload.update(
                    total_amount=parse_money(amount.value),
                    installment_count=parse_int(installments, "Taksit sayısı", required=True, minimum=2),
                )
            else:
                payload.update(amount=parse_money(amount.value), frequency=frequency.value, end_date=end.iso)
            await state.budget.plans.create(payload)
            toast(page, "Ödeme planı oluşturuldu. Ödemeler sekmesinden takip edebilirsiniz.")
        state.router.pop()
        await on_saved()

    async def delete():
        await state.budget.transactions.delete(txn["id"])
        state.router.pop()
        await on_saved()

    if is_edit:
        controls = [kind, amount, day.control, description, category, account, note]
        if txn.get("plan"):
            controls.insert(0, ft.Text("Bu işlem bir ödeme planından oluştu.", color=ft.Colors.GREY_600))
    else:
        controls = [kind, repeat_dd, amount, day.control, description, category, account,
                    frequency, end.control, installments, auto_pay, note]

    return form_view(
        state, "/entry", "İşlemi düzenle" if is_edit else "Yeni işlem", controls,
        on_save=save, on_delete=delete if is_edit else None,
    )
