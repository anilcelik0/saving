import asyncio

import flet as ft

from .choices import label
from .transactions import account_options, category_options
from .theme import EXPENSE, INCOME, MUTED, grouped, icon_badge
from .ui import FormError, confirm, dropdown, dropdown_value, empty_text, fmt_date, fmt_money, guarded, toast

GENERIC_WARNING = "Bu banka için özel okuyucu yok, genel okuyucu kullanıldı. Satırları kontrol edin."
STATUSES = [("pending", "Sırada"), ("parsing", "Okunuyor"), ("ready", "Onay bekliyor"),
            ("failed", "Hata"), ("imported", "Aktarıldı")]
TYPES = [("account", "Hesap ekstresi"), ("card", "Kart ekstresi")]
SKIP_REASONS = {
    "duplicate": "Daha önce aktarılmış",
    "card_payment": "Kart borcu ödemesi (kart ekstresinden gelir)",
    "transfer": "Kendi hesabına virman",
    "investment": "Yatırım / mevduat hareketi",
    "user": "Aktarılmayacak",
}
POLL_SECONDS, POLL_LIMIT = 1.5, 60


class StatementsScreen:
    """More > Statements: uploaded statements + upload button."""

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.picker = ft.FilePicker()
        self.list = ft.ListView(expand=True, padding=16, spacing=12)
        self.view = ft.View(
            route="/statements",
            appbar=ft.AppBar(title=ft.Text("Ekstreler")),
            floating_action_button=ft.FloatingActionButton(icon=ft.Icons.UPLOAD_FILE, on_click=lambda e: self._upload_dialog()),
            controls=[self.list],
        )
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        items = (await self.state.budget.statements.list(page_size=50))["results"]
        self.list.controls = grouped([self._tile(s) for s in items]) or [
            empty_text("Henüz ekstre yüklenmedi. PDF veya Excel hesap/kart ekstresi yükleyebilirsiniz.")
        ]
        self.page.update()

    def _tile(self, s):
        parts = [label(STATUSES, s["status"])]
        if s["bank"]:
            parts.append(f"{s['bank_label']} · {label(TYPES, s['statement_type'])}")
        if s["period_start"]:
            parts.append(f"{fmt_date(s['period_start'])} - {fmt_date(s['period_end'])}")
        if s["status"] == "imported":
            parts.append(f"{s['imported_count']} aktarıldı, {s['matched_count']} eşleşti, {s['cancelled_count']} iade")
        if s["exclude_from_balance"]:
            parts.append("Bakiyeye dahil değil")
        if s["error"]:
            parts.append(s["error"])
        parts.append(self.state.account_name(s["account"]))
        return ft.ListTile(
            leading=icon_badge(ft.Icons.DESCRIPTION, "#DC2626" if s["status"] == "failed" else "#1D4ED8", size=36),
            title=ft.Text(s["original_name"], weight=ft.FontWeight.W_500, max_lines=1,
                          overflow=ft.TextOverflow.ELLIPSIS),
            subtitle=ft.Text(" · ".join(parts), color=EXPENSE if s["status"] == "failed" else None),
            trailing=ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Ekstre bilgilerini sil", on_click=lambda e: confirm(
                self.page, "Ekstre kaydı ve satırları silinecek. Aktarılmış harcamalar kalır.",
                lambda: self._delete(s))),
            on_click=lambda e: self.state.router.push(StatementReview(self.state, s["id"], on_done=self.refresh).view),
        )

    async def _delete(self, s):
        await self.state.budget.statements.delete(s["id"])
        await self.refresh()

    def _upload_dialog(self):
        upload_dialog(self.state, self.picker, self.refresh)


def upload_dialog(state, picker: ft.FilePicker, on_done):
    """Choose account + file, upload, then open the preview. Used by the statements list and the + menu."""
    page = state.page
    accounts = account_options(state)
    if not accounts:
        toast(page, "Önce Diğer > Hesaplar bölümünden bir hesap ekleyin.", error=True)
        return
    account = dropdown("Hangi hesaba aktarılsın?", accounts, accounts[0][0])
    hint = ft.Text("Kart ekstresindeki harcamalar, kartın bağlı olduğu banka hesabına gider olarak eklenir.",
                   size=12, color=MUTED)
    history_only = ft.Checkbox(
        label="Bu ekstre bakiyeden düşülmesin (eski ekstre, sadece rapor için)", value=False,
    )

    async def pick_and_upload():
        files = await picker.pick_files(
            dialog_title="Ekstre seç", file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf", "xlsx"], with_data=True,
        )
        if not files:
            return
        f = files[0]
        if not f.bytes:
            raise FormError("Dosya okunamadı.")
        page.pop_dialog()
        statement = await state.budget.statements.upload(
            account.value, f.name, f.bytes, exclude_from_balance=bool(history_only.value)
        )
        state.router.push(StatementReview(state, statement["id"], on_done=on_done).view)

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Ekstre yükle"),
            content=ft.Column([account, hint, history_only], tight=True),
            actions=[
                ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()),
                ft.FilledButton("Dosya seç", on_click=guarded(page, pick_and_upload)),
            ],
        )
    )


class StatementReview:
    """Waits for parsing, then shows preview lines: include/exclude, category, match; confirm imports."""

    def __init__(self, state, statement_id, on_done):
        self.state = state
        self.page = state.page
        self.statement_id = statement_id
        self.on_done = on_done
        self.statement = None
        self.lines: list = []
        self.header = ft.Text("Ekstre okunuyor...")
        self.list = ft.ListView(expand=True)
        self.confirm_button = ft.FilledButton("Aktar", visible=False, on_click=guarded(self.page, self._confirm))
        self.delete_after = ft.Checkbox(
            label="Aktardıktan sonra ekstre bilgilerini sil (harcamalar kalır)", value=True, visible=False,
        )
        self.view = ft.View(
            route="/statement",
            appbar=ft.AppBar(title=ft.Text("Ekstre önizleme")),
            controls=[ft.Container(self.header, padding=ft.Padding.symmetric(horizontal=16)), self.list,
                      ft.Container(ft.Column([self.delete_after, self.confirm_button], tight=True), padding=16)],
            padding=0,
        )
        self.page.run_task(guarded(self.page, self._load))

    async def _load(self):
        for _ in range(POLL_LIMIT):
            self.statement = await self.state.budget.statements.get(self.statement_id)
            if self.statement["status"] not in ("pending", "parsing"):
                break
            await asyncio.sleep(POLL_SECONDS)
        s = self.statement
        if s["status"] == "failed":
            self.header.value = f"Ekstre okunamadı: {s['error']}"
            self.header.color = EXPENSE
            self.page.update()
            return
        if s["status"] in ("pending", "parsing"):
            self.header.value = "Ekstre hâlâ işleniyor. Daha sonra Ekstreler listesinden açabilirsiniz."
            self.page.update()
            return
        self.lines = await self.state.budget.statements.lines(self.statement_id)
        self._render()

    def _render(self):
        s = self.statement
        editable = s["status"] == "ready"
        selected = [line for line in self.lines if line["action"] != "skip"]
        expense = sum(float(line["amount"]) for line in selected if line["kind"] == "expense")
        income = sum(float(line["amount"]) for line in selected if line["kind"] == "income")
        self.header.value = (
            (f"⚠ {GENERIC_WARNING}\n" if s["is_generic"] else "")
            + f"{s['bank_label']} · {label(TYPES, s['statement_type'])} · "
            f"{fmt_date(s['period_start'])} - {fmt_date(s['period_end'])}\n"
            f"Seçili {len(selected)}/{len(self.lines)} satır · gider {fmt_money(expense)} · gelir {fmt_money(income)}"
            + ("" if editable else f"\nAktarıldı: {s['imported_count']} yeni, {s['matched_count']} eşleşti")
        )
        self.list.controls = [self._tile(line, editable) for line in self.lines] or [empty_text("Satır yok.")]
        self.confirm_button.visible = self.delete_after.visible = editable
        self.confirm_button.content = f"{len(selected)} satırı aktar"
        self.page.update()

    def _tile(self, line, editable):
        is_expense = line["kind"] == "expense"
        notes = [fmt_date(line["date"]), self.state.category_name(line["category"])]
        if line["installment"]:
            notes.append(f"Taksit: {line['installment']}")
        color = None
        if line["action"] == "refund" and line["refund_info"]:
            r = line["refund_info"]
            where = "bu ekstredeki" if r["in_statement"] else "daha önce aktarılan"
            notes = [fmt_date(line["date"]),
                     f"İade: {where} {fmt_date(r['date'])} tarihli '{r['description']}' harcamasını iptal edecek"]
            color = ft.Colors.ORANGE_800
        elif line["action"] == "match" and line["matched_info"]:
            m = line["matched_info"]
            notes.append(f"Bekleyen kayıtla eşleşecek: {m['description']} ({fmt_date(m['date'])})")
            color = ft.Colors.BLUE_700
        elif line["action"] == "skip":
            notes.append(SKIP_REASONS.get(line["skip_reason"], "Aktarılmayacak"))
            color = MUTED

        checkbox = ft.Checkbox(
            value=line["action"] != "skip",
            disabled=not editable or line["skip_reason"] == "duplicate",
            on_change=lambda e: self.page.run_task(guarded(self.page, lambda: self._toggle(line, e.control.value))),
        )
        return ft.ListTile(
            leading=checkbox,
            title=ft.Text(line["description"]),
            subtitle=ft.Text(" · ".join(filter(None, notes)), color=color),
            trailing=ft.Text(("-" if is_expense else "+") + fmt_money(line["amount"]),
                             color=EXPENSE if is_expense else INCOME),
            on_click=(lambda e: self._edit_dialog(line)) if editable and line["skip_reason"] != "duplicate" else None,
        )

    async def _update(self, line, data):
        updated = await self.state.budget.statements.update_line(line["id"], data)
        self.lines = [updated if x["id"] == line["id"] else x for x in self.lines]
        self._render()

    @staticmethod
    def _has_refund_target(line):
        return bool(line["refund_target_line"] or (line["refund_info"] and not line["refund_info"]["in_statement"]))

    async def _toggle(self, line, include):
        if not include:
            action = "skip"
        elif self._has_refund_target(line):
            action = "refund"
        else:
            action = "match" if line["matched_transaction"] else "import"
        await self._update(line, {"action": action})

    def _edit_dialog(self, line):
        page = self.page
        actions = [("import", "Gelir/gider olarak aktar"), ("skip", "Aktarma")]
        if self._has_refund_target(line):
            actions.insert(0, ("refund", "İade: ilgili harcamayı iptal et"))
        elif line["matched_transaction"]:
            actions.insert(0, ("match", "Bekleyen kayıtla eşleştir (ödendi yap)"))
        action = dropdown("İşlem", actions, line["action"])
        category = dropdown("Kategori", category_options(self.state, line["kind"], line["category"]),
                            line["category"], with_none=True)

        async def save():
            new_category = dropdown_value(category)
            await self._update(line, {"action": action.value, "category": new_category})
            page.pop_dialog()
            if new_category != line["category"]:
                # backend learned merchant -> category and updated same-merchant lines: reload them
                self.lines = await self.state.budget.statements.lines(self.statement_id)
                self._render()
                toast(page, "Kategori hatırlanacak; aynı işyerinin diğer satırları da güncellendi.")

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(line["description"]),
                content=ft.Column([ft.Text(f"{fmt_date(line['date'])} · {fmt_money(line['amount'])}"), action, category],
                                  tight=True),
                actions=[ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()),
                         ft.FilledButton("Kaydet", on_click=guarded(page, save))],
            )
        )

    async def _confirm(self):
        self.statement = await self.state.budget.statements.confirm(
            self.statement_id, delete_after=bool(self.delete_after.value)
        )
        s = self.statement
        message = f"{s['imported_count']} kayıt aktarıldı, {s['matched_count']} kayıt eşleşti."
        if s["cancelled_count"]:
            message += f" {s['cancelled_count']} harcama iade nedeniyle iptal edildi."
        if s["deleted"]:
            message += " Ekstre bilgileri silindi."
        toast(self.page, message)
        self.state.router.pop()
        await self.on_done()

