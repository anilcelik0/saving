from datetime import date

import flet as ft

from .choices import FREQUENCIES, KINDS, NONE, REPEATS
from .ui import (
    DateInput, FormError, ask_scope, dropdown, dropdown_value, fmt_date, fmt_money, form_view, guarded,
    int_field, money_field, parse_int, parse_money, text_field, toast,
)


def transaction_tile(state, t, on_changed) -> ft.ListTile:
    """Row for both pending and paid transactions. Pending manual ones get a quick pay button."""
    is_expense = t["kind"] == "expense"
    title = t["description"] or state.category_name(t["category"])
    if t["series_info"]:
        title += f" ({t['series_info']['label']})"

    where = state.card_name(t["account"]) if t.get("is_card") else state.account_name(t["account"])
    details = [fmt_date(t["date"]), state.category_name(t["category"]), where]
    cancelled = t["status"] == "cancelled"
    if t["status"] == "pending":
        details.insert(0, "Gecikti" if t["is_overdue"] else ("Otomatik" if t["auto_pay"] else "Bekliyor"))
    elif cancelled:
        details.insert(0, "İptal edildi")

    amount_text = ft.Text(
        ("-" if is_expense else "+") + fmt_money(t["amount"]),
        color=ft.Colors.GREY_500 if cancelled else (ft.Colors.RED_700 if is_expense else ft.Colors.GREEN_700),
    )
    if t["status"] == "pending" and not t["auto_pay"]:
        trailing = ft.Row(
            [amount_text, ft.TextButton("Alındı" if not is_expense else "Öde",
                                        on_click=lambda e: pay_dialog(state, t, on_changed))],
            tight=True,
        )
    else:
        trailing = amount_text

    subtitle_color = ft.Colors.RED_700 if t["is_overdue"] else (ft.Colors.GREY_500 if cancelled else None)
    return ft.ListTile(
        title=ft.Text(title, color=ft.Colors.GREY_500 if cancelled else None),
        subtitle=ft.Text(" · ".join(filter(None, details)), color=subtitle_color),
        trailing=trailing,
        on_click=lambda e: open_entry_form(state, t, on_changed),
    )


def pay_dialog(state, t, on_done):
    """Mark a pending transaction as paid; amount may differ (e.g. bill came higher)."""
    page = state.page
    amount = money_field("Tutar", t["amount"])
    day = DateInput(page, "Ödeme tarihi", date.today())

    async def pay():
        await state.budget.transactions.pay(t["id"], amount=parse_money(amount.value), date=day.iso)
        page.pop_dialog()
        toast(page, "Ödendi olarak işaretlendi.")
        await on_done()

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(t["description"] or "Ödeme"),
            content=ft.Column([amount, day.control], tight=True),
            actions=[
                ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()),
                ft.FilledButton("Kaydet", on_click=guarded(page, pay)),
            ],
        )
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


def entry_form(state, txn: dict | None, on_saved, default_repeat="none") -> ft.View:
    """
    New entry: one-time / recurring / installment (backend creates the dated transactions).
    Existing entry: edit; for series occurrences ask "only this" or "this and following".
    """
    txn = txn or {}
    page = state.page
    is_edit = bool(txn.get("id"))
    in_series = bool(txn.get("series"))
    accounts = account_options(state, txn.get("account"))

    kind = dropdown("Tür", KINDS, txn.get("kind", "expense"))
    kind.disabled = in_series
    repeat = dropdown("Tekrar", REPEATS, default_repeat)
    amount = money_field("Tutar", txn.get("amount"))
    day = DateInput(page, "Tarih", txn.get("date") or date.today())
    description = text_field("Açıklama", txn.get("description"))
    category = dropdown(
        "Kategori", category_options(state, kind.value, txn.get("category")), txn.get("category"), with_none=True
    )
    account = dropdown("Hesap", accounts, txn.get("account") or accounts[0][0])
    frequency = dropdown("Sıklık", FREQUENCIES, "monthly")
    end = DateInput(page, "Bitiş tarihi (boş = süresiz)", optional=True)
    installments = int_field("Taksit sayısı")
    auto_pay = ft.Switch(label="Vade gününde otomatik ödendi say", value=txn.get("auto_pay", False))
    is_card = ft.Switch(label="Kredi kartıyla (özette ekstre dönemine göre sayılır)", value=txn.get("is_card", False))
    note = text_field("Not", txn.get("note"), multiline=True)

    def account_has_card():
        return any(a["id"] == account.value and a.get("statement_day") for a in state.accounts)

    def refresh_visibility():
        mode = repeat.value
        amount.label = "Toplam tutar" if mode == "installment" else "Tutar"
        day.text.label = "Tarih" if mode == "none" else "İlk ödeme tarihi"
        frequency.visible = end.control.visible = mode == "recurring"
        installments.visible = mode == "installment"
        is_card.visible = account_has_card() or is_card.value

    def account_changed(e):
        refresh_visibility()
        page.update()

    account.on_select = account_changed

    def kind_changed(e):
        set_category_options(category, state, kind.value)
        page.update()

    def repeat_changed(e):
        refresh_visibility()
        page.update()

    kind.on_select = kind_changed
    repeat.on_select = repeat_changed
    refresh_visibility()

    def base_payload():
        return {
            "kind": kind.value,
            "amount": parse_money(amount.value),
            "date": day.iso,
            "description": description.value,
            "category": dropdown_value(category),
            "account": account.value,
            "auto_pay": auto_pay.value,
            "is_card": bool(is_card.value and account_has_card()),
            "note": note.value,
        }

    async def done():
        state.router.pop()
        await on_saved()

    async def save():
        payload = base_payload()
        if is_edit:
            if in_series:
                async def update(scope):
                    data = dict(payload)
                    if scope == "following":
                        data.pop("date")  # dates stay per occurrence
                    await state.budget.transactions.update(txn["id"], data, scope=scope)
                    await done()

                ask_scope(page, "Değişiklik nereye uygulansın?", update)
                return
            await state.budget.transactions.update(txn["id"], payload)
            return await done()

        mode = repeat.value
        payload["repeat"] = mode
        if mode != "none" and not description.value:
            raise FormError("Tekrarlayan kayıtlar için açıklama gerekli.")
        if mode == "recurring":
            payload.update(frequency=frequency.value, end_date=end.iso)
        elif mode == "installment":
            payload["installment_count"] = parse_int(installments, "Taksit sayısı", required=True, minimum=2)
        await state.budget.transactions.create(payload)
        if mode != "none":
            toast(page, "Kayıtlar oluşturuldu. Hareketler sekmesinde tarihleriyle görünür.")
        await done()

    async def delete():
        if in_series:
            async def remove(scope):
                await state.budget.transactions.delete(txn["id"], scope=scope)
                await done()

            ask_scope(page, "Hangi kayıtlar silinsin?", remove,
                      following_text="Bu ve sonraki bekleyenler (tekrar durur)")
            return
        await state.budget.transactions.delete(txn["id"])
        await done()

    async def toggle_paid():
        if txn["status"] == "paid":
            await state.budget.transactions.unpay(txn["id"])
            await done()
        else:
            pay_dialog(state, txn, done)

    async def toggle_cancel():
        if txn["status"] == "cancelled":
            await state.budget.transactions.restore(txn["id"])
        else:
            await state.budget.transactions.cancel(txn["id"])
        await done()

    if is_edit:
        status = txn["status"]
        if status == "paid":
            status_text = "Ödendi" + (f" ({fmt_date(txn['paid_on'])})" if txn.get("paid_on") else "")
        elif status == "cancelled":
            status_text = "İptal edildi (bakiyeye ve özete dahil değil)"
        else:
            status_text = "Gecikti" if txn["is_overdue"] else "Bekliyor"
        header = [ft.Text(f"Durum: {status_text}" + (f" · Seri {txn['series_info']['label']}" if in_series else ""),
                          color=ft.Colors.GREY_700)]
        buttons = []
        if status != "cancelled":
            buttons.append(ft.OutlinedButton(
                "Ödenmedi olarak geri al" if status == "paid" else "Ödendi işaretle",
                on_click=guarded(page, toggle_paid),
            ))
        cancel_text = "İptali geri al" if status == "cancelled" else (
            "İptal et (iade edildi)" if status == "paid" else "Bu seferlik atla (iptal et)")
        buttons.append(ft.OutlinedButton(cancel_text, on_click=guarded(page, toggle_cancel)))
        controls = header + [kind, amount, day.control, description, category, account, is_card, auto_pay, note,
                             *buttons]
    else:
        controls = [kind, repeat, amount, day.control, description, category, account, is_card,
                    frequency, end.control, installments, auto_pay, note]

    return form_view(
        state, "/entry", "Kaydı düzenle" if is_edit else "Yeni kayıt", controls,
        on_save=save, on_delete=delete if is_edit else None,
    )
