import asyncio

import flet as ft

from .choices import label
from .transactions import account_options, category_options
from .ui import FormError, dropdown, dropdown_value, empty_text, fmt_date, fmt_money, guarded, toast

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
        self.list = ft.ListView(expand=True)
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
        self.list.controls = [self._tile(s) for s in items] or [
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
            parts.append(f"{s['imported_count']} aktarıldı, {s['matched_count']} eşleşti")
        if s["error"]:
            parts.append(s["error"])
        return ft.ListTile(
            title=ft.Text(s["original_name"]),
            subtitle=ft.Text(" · ".join(parts), color=ft.Colors.RED_700 if s["status"] == "failed" else None),
            trailing=ft.Text(self.state.account_name(s["account"])),
            on_click=lambda e: self.state.router.push(StatementReview(self.state, s["id"], on_done=self.refresh).view),
        )

    def _upload_dialog(self):
        page = self.page
        accounts = account_options(self.state)
        if not accounts:
            toast(page, "Önce Diğer > Hesaplar bölümünden bir hesap ekleyin.", error=True)
            return
        account = dropdown("Hangi hesaba aktarılsın?", accounts, accounts[0][0])
        hint = ft.Text("Kart ekstresindeki harcamalar, kartın bağlı olduğu banka hesabına gider olarak eklenir.",
                       size=12, color=ft.Colors.GREY_700)

        async def pick_and_upload():
            files = await self.picker.pick_files(
                dialog_title="Ekstre seç", file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf", "xlsx"], with_data=True,
            )
            if not files:
                return
            f = files[0]
            if not f.bytes:
                raise FormError("Dosya okunamadı.")
            page.pop_dialog()
            statement = await self.state.budget.statements.upload(account.value, f.name, f.bytes)
            self.state.router.push(StatementReview(self.state, statement["id"], on_done=self.refresh).view)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Ekstre yükle"),
                content=ft.Column([account, hint], tight=True),
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
        self.view = ft.View(
            route="/statement",
            appbar=ft.AppBar(title=ft.Text("Ekstre önizleme")),
            controls=[ft.Container(self.header, padding=ft.Padding.symmetric(horizontal=16)), self.list,
                      ft.Container(self.confirm_button, padding=16)],
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
            self.header.color = ft.Colors.RED_700
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
        self.confirm_button.visible = editable
        self.confirm_button.content = f"{len(selected)} satırı aktar"
        self.page.update()

    def _tile(self, line, editable):
        is_expense = line["kind"] == "expense"
        notes = [fmt_date(line["date"]), self.state.category_name(line["category"])]
        if line["installment"]:
            notes.append(f"Taksit: {line['installment']}")
        color = None
        if line["action"] == "match" and line["matched_info"]:
            m = line["matched_info"]
            notes.append(f"Bekleyen kayıtla eşleşecek: {m['description']} ({fmt_date(m['date'])})")
            color = ft.Colors.BLUE_700
        elif line["action"] == "skip":
            notes.append(SKIP_REASONS.get(line["skip_reason"], "Aktarılmayacak"))
            color = ft.Colors.GREY_600

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
                             color=ft.Colors.RED_700 if is_expense else ft.Colors.GREEN_700),
            on_click=(lambda e: self._edit_dialog(line)) if editable and line["skip_reason"] != "duplicate" else None,
        )

    async def _update(self, line, data):
        updated = await self.state.budget.statements.update_line(line["id"], data)
        self.lines = [updated if x["id"] == line["id"] else x for x in self.lines]
        self._render()

    async def _toggle(self, line, include):
        if include:
            action = "match" if line["matched_transaction"] else "import"
        else:
            action = "skip"
        await self._update(line, {"action": action})

    def _edit_dialog(self, line):
        page = self.page
        actions = [("import", "Yeni kayıt olarak aktar"), ("skip", "Aktarma")]
        if line["matched_transaction"]:
            actions.insert(0, ("match", "Bekleyen kayıtla eşleştir (ödendi yap)"))
        action = dropdown("İşlem", actions, line["action"])
        category = dropdown("Kategori", category_options(self.state, line["kind"], line["category"]),
                            line["category"], with_none=True)

        async def save():
            await self._update(line, {"action": action.value, "category": dropdown_value(category)})
            page.pop_dialog()

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
        self.statement = await self.state.budget.statements.confirm(self.statement_id)
        toast(self.page, f"{self.statement['imported_count']} kayıt aktarıldı, {self.statement['matched_count']} kayıt eşleşti.")
        self.state.router.pop()
        await self.on_done()

