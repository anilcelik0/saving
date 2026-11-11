from datetime import date

import flet as ft

from .choices import FREQUENCIES, KINDS, NONE
from .form_kit import (
    CategoryGrid, Chips, Collapsible, DateChips, QuickForm, Segmented, big_amount, field, hero,
    plain_input,
)
from .theme import EXPENSE, INCOME, MUTED, kind_badge, muted
from .ui import (
    FormError, ask_scope, fmt_date, fmt_money, fmt_number, guarded, parse_int, parse_money,
    toast,
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
        color=MUTED if cancelled else (EXPENSE if is_expense else INCOME), weight=ft.FontWeight.W_600,
    )
    if t["status"] == "pending" and not t["auto_pay"]:
        trailing = ft.Row(
            [amount_text, ft.TextButton("Alındı" if not is_expense else "Öde",
                                        on_click=lambda e: pay_dialog(state, t, on_changed))],
            tight=True,
        )
    else:
        trailing = amount_text

    subtitle_color = EXPENSE if t["is_overdue"] else (MUTED if cancelled else MUTED)
    return ft.ListTile(
        leading=kind_badge(t["kind"], card_spend=t.get("is_card", False), dimmed=cancelled),
        title=ft.Text(title, color=MUTED if cancelled else None, weight=ft.FontWeight.W_500,
                      max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        subtitle=ft.Text(" · ".join(filter(None, details)), color=subtitle_color),
        trailing=trailing,
        on_click=lambda e: open_entry_form(state, t, on_changed),
    )


def pay_dialog(state, t, on_done):
    """Mark a pending transaction as paid; amount may differ (e.g. bill came higher)."""
    page = state.page
    amount = big_amount(t["amount"])
    amount.text_style = ft.TextStyle(size=32, weight=ft.FontWeight.W_800)
    day = DateChips(page, date.today())

    async def pay():
        await state.budget.transactions.pay(t["id"], amount=parse_money(amount.value), date=day.iso)
        page.pop_dialog()
        toast(page, "Ödendi olarak işaretlendi.")
        await on_done()

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(t["description"] or "Ödeme"),
            content=ft.Column([muted("Ödenen tutar", size=13), amount, field("Ödeme tarihi", day.control)],
                              tight=True, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            actions=[
                ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()),
                ft.FilledButton("Ödendi işaretle", on_click=guarded(page, pay)),
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


REPEAT_CHIPS = [("none", "Tek seferlik"), ("recurring", "Düzenli"), ("installment", "Taksitli")]
KIND_COLORS = {"expense": (ft.Colors.ERROR_CONTAINER, EXPENSE), "income": (ft.Colors.TERTIARY_CONTAINER, INCOME)}


def amount_preview(text) -> str | None:
    """'1.250,5' -> '1.250,5 ₺' for live button labels; None while the input is not a valid amount."""
    try:
        return fmt_number(parse_money(text)) + " ₺"
    except FormError:
        return None


def entry_form(state, txn: dict | None, on_saved, default_repeat="none") -> ft.View:
    """
    New entry: one-time / recurring / installment (backend creates the dated transactions).
    Existing entry: edit; for series occurrences ask "only this" or "this and following".
    Card spending is a separate account chip ("Enpara kartı") instead of a switch.
    """
    txn = txn or {}
    page = state.page
    settings = state.settings
    is_edit = bool(txn.get("id"))
    in_series = bool(txn.get("series"))
    accounts = [a for a in state.accounts if not a["is_archived"] or a["id"] == txn.get("account")]

    account_chips = []
    for a in accounts:
        account_chips.append((a["id"], a["name"]))
        if a.get("statement_day") or (a["id"] == txn.get("account") and txn.get("is_card")):
            account_chips.append((f"{a['id']}|card", state.card_name(a["id"])))
    preferred = settings.default_account if settings else None
    if preferred not in {a["id"] for a in accounts}:
        preferred = accounts[0]["id"]
    initial_account = txn.get("account") or preferred
    if txn.get("is_card"):
        initial_account += "|card"

    def categories_for(kind_key):
        return [c for c in state.categories
                if c["kind"] == kind_key and (not c["is_archived"] or c["id"] == txn.get("category"))]

    # ---- controls
    amount_label = muted("Tutar", size=13)
    amount = big_amount(txn.get("amount"), on_change=lambda e: refresh())
    description = ft.TextField(
        value=txn.get("description") or "", hint_text="ör. Migros, Kira, Maaş",
        prefix_icon=ft.Icons.EDIT_NOTE, text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_600),
        capitalization=ft.TextCapitalization.SENTENCES,
    )
    kind = Segmented(KINDS, txn.get("kind", "expense"), on_change=lambda k: kind_changed(k), colors=KIND_COLORS,
                     disabled=in_series)
    category = CategoryGrid(categories_for(kind.value), txn.get("category"),
                            recent=settings.recent_categories if settings else None)
    account = Chips(account_chips, initial_account)
    day = DateChips(page, txn.get("date") or date.today())
    day_field = field("Tarih", day.control)

    repeat = Chips(REPEAT_CHIPS, default_repeat, on_change=lambda k: refresh())
    frequency = Chips(FREQUENCIES, "monthly")
    end = DateChips(page, None, optional=True, shortcuts=False)
    installments = plain_input(hint="ör. 6", number=True)
    auto_pay = ft.Switch(label="Vade gününde otomatik ödendi say", value=txn.get("auto_pay", False))
    note = plain_input(txn.get("note"), hint="Not (isteğe bağlı)", multiline=True)
    frequency_field = field("Sıklık", frequency.control)
    end_field = field("Bitiş tarihi (boş = süresiz)", end.control)
    installments_field = field("Taksit sayısı", installments)

    def extras_summary():
        if is_edit:
            return "Otomatik" if auto_pay.value else ("Not var" if note.value else "")
        return dict(REPEAT_CHIPS).get(repeat.value, "")

    if is_edit:
        extras = Collapsible("Otomatik ödeme ve not", [auto_pay, note], extras_summary)
    else:
        extras = Collapsible("Tekrar, taksit, not",
                             [field("Tekrar", repeat.control), frequency_field, end_field, installments_field,
                              auto_pay, note],
                             extras_summary, expanded=default_repeat != "none")

    def kind_changed(key):
        category.set_categories(categories_for(key))
        repeat.set_options([c for c in REPEAT_CHIPS if key == "expense" or c[0] != "installment"], repeat.value)
        refresh()

    def refresh():
        mode = "none" if is_edit else repeat.value
        amount_label.value = "Toplam tutar" if mode == "installment" else "Tutar"
        day_field.controls[0].value = "Tarih" if mode == "none" else "İlk ödeme tarihi"
        frequency_field.visible = end_field.visible = mode == "recurring"
        installments_field.visible = mode == "installment"
        extras.refresh()
        if is_edit:
            form.set_action("Değişiklikleri kaydet")
        else:
            shown = amount_preview(amount.value)
            word = "gider" if kind.value == "expense" else "gelir"
            form.set_action(f"{shown} {word} ekle" if shown else f"{word.capitalize()} ekle")
        try:
            page.update()
        except RuntimeError:
            pass

    def base_payload():
        account_id, _, card = (account.value or "").partition("|")
        return {
            "kind": kind.value,
            "amount": parse_money(amount.value),
            "date": day.iso,
            "description": description.value,
            "category": category.value,
            "account": account_id,
            "auto_pay": auto_pay.value,
            "is_card": bool(card),
            "note": note.value,
        }

    async def done():
        state.router.pop()
        await on_saved()

    async def saved(payload):
        if settings:
            await settings.remember_category(payload["category"])
        await done()

    async def save():
        if not account.value:
            raise FormError("Bir hesap seçin.")
        payload = base_payload()
        if is_edit:
            if in_series:
                async def update(scope):
                    data = dict(payload)
                    if scope == "following":
                        data.pop("date")  # dates stay per occurrence
                    await state.budget.transactions.update(txn["id"], data, scope=scope)
                    await saved(payload)

                ask_scope(page, "Değişiklik nereye uygulansın?", update)
                return
            await state.budget.transactions.update(txn["id"], payload)
            return await saved(payload)

        mode = repeat.value
        payload["repeat"] = mode
        if mode != "none" and not description.value:
            raise FormError("Tekrarlayan kayıtlar için isim gerekli.")
        if mode == "recurring":
            payload.update(frequency=frequency.value, end_date=end.iso)
        elif mode == "installment":
            payload["installment_count"] = parse_int(installments, "Taksit sayısı", required=True, minimum=2)
        await state.budget.transactions.create(payload)
        if mode != "none":
            toast(page, "Kayıtlar oluşturuldu. Hareketler sekmesinde tarihleriyle görünür.")
        await saved(payload)

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

    body = [
        hero(amount_label, amount),
        field("İsim", description),
        field("Kategori", category.control),
        field("Hesap", account.control),
        day_field,
        extras.control,
    ]
    if is_edit:
        status = txn["status"]
        if status == "paid":
            status_text = "Ödendi" + (f" ({fmt_date(txn['paid_on'])})" if txn.get("paid_on") else "")
        elif status == "cancelled":
            status_text = "İptal edildi (bakiyeye ve özete dahil değil)"
        else:
            status_text = "Gecikti" if txn["is_overdue"] else "Bekliyor"
        buttons = []
        if status != "cancelled":
            buttons.append(ft.OutlinedButton(
                "Ödenmedi olarak geri al" if status == "paid" else "Ödendi işaretle",
                on_click=guarded(page, toggle_paid),
            ))
        cancel_text = "İptali geri al" if status == "cancelled" else (
            "İptal et (iade edildi)" if status == "paid" else "Bu seferlik atla (iptal et)")
        buttons.append(ft.OutlinedButton(cancel_text, on_click=guarded(page, toggle_cancel)))
        series = f" · Seri {txn['series_info']['label']}" if in_series else ""
        body.append(field("Durum", ft.Column([muted(status_text + series, size=13), ft.Row(buttons, wrap=True)],
                                             spacing=8)))

    form = QuickForm(state, "/entry", body, on_save=save, center=kind.control,
                     on_delete=delete if is_edit else None)
    refresh()
    return form.view
