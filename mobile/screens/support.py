"""
"Sorun bildir": report form (topic, message, optional statement + files with consent) and Diğer > Bildirimlerim.
Technical context (app version, platform, open screen, error message) is attached automatically and shown to the
user before sending. A statement uploaded in this session is still in memory on the device (the server deletes the
file right after parsing), so it can be attached without picking it again.
"""

import flet as ft

from config import APP_VERSION, is_packaged

from .form_kit import Chips, QuickForm, field
from .theme import ACCENT, EXPENSE, INCOME, MUTED, card, grouped, icon_badge, muted
from .ui import FormError, empty_text, fmt_date, guarded, toast

CATEGORIES = [("bug", "Hata"), ("statement", "Ekstre sorunu"), ("suggestion", "Öneri"), ("other", "Diğer")]
HINTS = {
    "bug": "Ne yapıyordunuz, ne olmasını bekliyordunuz, ne oldu?",
    "statement": "Ne yanlış okundu? Ör. 12.11 tarihli Migros harcaması gelmedi, tutar yanlış, ekstre hiç okunmadı...",
    "suggestion": "Neyi daha iyi yapabiliriz?",
    "other": "Mesajınız",
}
BADGES = {
    "bug": (ft.Icons.BUG_REPORT, "#DC2626"), "statement": (ft.Icons.DESCRIPTION, "#1D4ED8"),
    "suggestion": (ft.Icons.LIGHTBULB, "#D97706"), "other": (ft.Icons.HELP_OUTLINE, "#64748B"),
}
STATUS_COLORS = {"in_progress": ACCENT, "resolved": INCOME}
ATTACH_EXTENSIONS = ["png", "jpg", "jpeg", "webp", "pdf", "xlsx", "xls", "csv", "txt"]
MAX_FILES, MAX_TOTAL_MB = 3, 18  # server: 3 files, 10 MB each; nginx body limit 20 MB
CONSENT_TEXT = ("Eklediğim dosyaların sorunun incelenmesi için gönderilmesini onaylıyorum. "
                "Dosyalar sorun çözülünce, en geç 30 gün içinde silinir.")


def report_context(state, error: str | None = None) -> dict:
    """Technical info of the screen that is open right now (shown in the form before sending)."""
    page = state.page
    screen = page.views[-1].route if page.views else ""
    if screen == "/" and state.home:
        screen = f"/ ({state.home.tabs[state.home.index].title})"
    context = {
        "app_version": APP_VERSION,
        "platform": getattr(page.platform, "value", str(page.platform)),
        "build": "release" if is_packaged() else "dev",
        "screen": screen,
    }
    if error:
        context["error"] = error[:500]
    return context


def _check_row(box: ft.Checkbox, text: ft.Text) -> ft.Row:
    """Checkbox with a wrapping label."""
    return ft.Row([box, ft.Container(text, expand=True, padding=ft.Padding.only(top=10))],
                  vertical_alignment=ft.CrossAxisAlignment.START, spacing=4)


def _statement_label(s: dict) -> str:
    name = s.get("bank_label") or s["original_name"]
    if s.get("period_start"):
        when = f"{fmt_date(s['period_start'])} - {fmt_date(s['period_end'])}"
    else:
        when = fmt_date(s["created_at"])
    return f"{name} · {when}" + (" · hata" if s["status"] == "failed" else "")


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(n // 1024, 1)} KB"


def report_form(state, category: str = "bug", related_statement: str | None = None, context: dict | None = None,
                on_sent=None) -> ft.View:
    page = state.page
    context = context or report_context(state)
    picker = ft.FilePicker()
    attachments: list[tuple[str, bytes]] = []
    current = {"loaded": False, "picked": None}  # picked: statement file chosen again from the phone

    kind = Chips(CATEGORIES, category, on_change=lambda k: kind_changed(k))
    message = ft.TextField(multiline=True, min_lines=4, max_lines=10, max_length=4000, hint_text=HINTS[category],
                           capitalization=ft.TextCapitalization.SENTENCES)

    statements = Chips([], related_statement, allow_none=True, on_change=lambda k: statement_changed())
    statement_hint = muted("", size=12)
    include_box = ft.Checkbox(value=True, on_change=lambda e: refresh())
    include_text = ft.Text("", size=13)
    include_row = _check_row(include_box, include_text)
    pick_button = ft.OutlinedButton("Ekstre dosyasını seç", icon=ft.Icons.UPLOAD_FILE)
    statement_field = field("Hangi ekstre?", ft.Column([statements.control, statement_hint, include_row, pick_button],
                                                        spacing=8))

    files_column = ft.Column(spacing=2)
    add_button = ft.OutlinedButton("Dosya / ekran görüntüsü ekle", icon=ft.Icons.ATTACH_FILE)
    consent_box = ft.Checkbox(value=False)
    consent_row = _check_row(consent_box, ft.Text(CONSENT_TEXT, size=13))

    tech = muted("Rapora otomatik eklenecek: " + " · ".join(
        [f"sürüm {context['app_version']}", context["platform"], f"ekran {context['screen']}"]), size=12)
    tech_lines = [tech]
    if context.get("error"):
        tech_lines.append(muted(f"Hata mesajı: {context['error']}", size=12, color=EXPENSE))

    def statement_file():
        """(name, bytes) of the selected statement to send, or None."""
        sid = statements.value
        if kind.value != "statement" or not sid:
            return None
        if sid in state.statement_files:
            return state.statement_files[sid] if include_box.value else None
        return current["picked"]

    def all_files():
        extra = statement_file()
        return attachments + ([extra] if extra else [])

    def refresh():
        is_statement = kind.value == "statement"
        statement_field.visible = is_statement
        sid = statements.value
        in_memory = bool(sid) and sid in state.statement_files
        include_row.visible = is_statement and in_memory
        pick_button.visible = is_statement and bool(sid) and not in_memory
        if in_memory:
            name, content = state.statement_files[sid]
            include_text.value = f"Yüklediğim ekstre dosyasını ekle ({name}, {_size(len(content))})"
        if current["picked"]:
            pick_button.content = f"Seçilen: {current['picked'][0]} · değiştir"
        if not current["loaded"]:
            statement_hint.value = "Ekstreler yükleniyor..."
        elif not statements.options:
            statement_hint.value = "Henüz yüklenmiş ekstre yok."
        elif not sid:
            statement_hint.value = "Sorun yaşadığınız ekstreyi seçin."
        elif in_memory:
            statement_hint.value = "Bu ekstreyi bu oturumda yüklediğiniz için dosyası cihazda hazır."
        else:
            statement_hint.value = ("Ekstre dosyaları güvenlik için okunduktan hemen sonra sunucudan silinir. "
                                    "İncelememiz için aynı dosyayı tekrar seçebilirsiniz (isteğe bağlı).")
        files_column.controls = [
            ft.Row([ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, size=18, color=MUTED),
                    ft.Text(f"{name} · {_size(len(content))}", size=13, expand=True, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18, tooltip="Kaldır",
                                  on_click=lambda e, i=i: remove_file(i))])
            for i, (name, content) in enumerate(attachments)
        ]
        add_button.disabled = len(all_files()) >= MAX_FILES
        consent_row.visible = bool(all_files())
        try:
            page.update()
        except RuntimeError:
            pass

    def remove_file(index):
        attachments.pop(index)
        refresh()

    def kind_changed(key):
        message.hint_text = HINTS[key]
        if key == "statement" and not current["loaded"]:
            page.run_task(guarded(page, load_statements))
        refresh()

    def statement_changed():
        current["picked"] = None  # a file picked for another statement does not belong to this one
        refresh()

    async def load_statements():
        items = (await state.budget.statements.list(page_size=15))["results"]
        statements.set_options([(s["id"], _statement_label(s)) for s in items], statements.value)
        current["loaded"] = True
        refresh()

    async def pick_statement():
        files = await picker.pick_files(dialog_title="Ekstre seç", file_type=ft.FilePickerFileType.CUSTOM,
                                        allowed_extensions=["pdf", "xlsx"], with_data=True)
        if files and files[0].bytes:
            current["picked"] = (files[0].name, files[0].bytes)
            refresh()

    async def add_files():
        files = await picker.pick_files(dialog_title="Dosya ekle", file_type=ft.FilePickerFileType.CUSTOM,
                                        allowed_extensions=ATTACH_EXTENSIONS, allow_multiple=True, with_data=True)
        for f in files or []:
            if f.bytes and len(all_files()) < MAX_FILES:
                attachments.append((f.name, f.bytes))
        refresh()

    pick_button.on_click = guarded(page, pick_statement)
    add_button.on_click = guarded(page, add_files)

    async def save():
        text = (message.value or "").strip()
        if len(text) < 5:
            raise FormError("Lütfen sorunu birkaç kelimeyle anlatın.")
        files = all_files()
        if len(files) > MAX_FILES:
            raise FormError(f"En fazla {MAX_FILES} dosya eklenebilir.")
        if sum(len(content) for _, content in files) > MAX_TOTAL_MB * 1024 * 1024:
            raise FormError(f"Dosyaların toplamı en fazla {MAX_TOTAL_MB} MB olabilir.")
        if files and not consent_box.value:
            raise FormError("Dosyaları göndermek için onay kutusunu işaretleyin.")
        sid = statements.value if kind.value == "statement" else None
        await state.support.report(
            category=kind.value, message=text, context=context,
            related_type="saving.statement" if sid else "", related_id=sid or "",
            attachments=attachments, statement_file=statement_file(), consent=bool(files),
        )
        state.router.pop()
        toast(page, "Teşekkürler, bildiriminiz alındı. Durumunu Diğer > Bildirimlerim'den takip edebilirsiniz.")
        if on_sent:
            await on_sent()

    body = [
        field("Konu", kind.control),
        field("Ne oldu?", message),
        statement_field,
        field("Ekler (isteğe bağlı)", ft.Column([files_column, add_button], spacing=4)),
        consent_row,
        card(ft.Column(tech_lines, spacing=4), padding=12),
    ]
    form = QuickForm(state, "/report", body, on_save=save, title="Sorun bildir", action_text="Gönder")
    if category == "statement":
        page.run_task(guarded(page, load_statements))
    refresh()
    return form.view


class MyReportsScreen:
    """Diğer > Bildirimlerim: the user's reports with status and the developer's response."""

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True, padding=16, spacing=12)
        self.view = ft.View(
            route="/my-reports",
            appbar=ft.AppBar(title=ft.Text("Bildirimlerim"), actions=[
                ft.IconButton(ft.Icons.ADD, tooltip="Yeni bildirim", on_click=lambda e: self._new())]),
            controls=[self.list],
            padding=0,
        )
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        reports = await self.state.support.reports()
        rows = []
        for r in reports:
            icon, color = BADGES.get(r["category"], BADGES["other"])
            sub = f"{r['status_label']} · {fmt_date(r['created_at'])}" + (" · yanıt var" if r["response"] else "")
            rows.append(ft.ListTile(
                leading=icon_badge(icon, color, size=36),
                title=ft.Text(r["message"].splitlines()[0], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                              weight=ft.FontWeight.W_500),
                subtitle=muted(sub, color=STATUS_COLORS.get(r["status"], MUTED)),
                on_click=lambda e, r=r: self._detail(r),
            ))
        self.list.controls = grouped(rows, empty_text(
            "Henüz bildirim göndermediniz. Bir sorunla karşılaşırsanız ekranın sağ üstündeki böcek simgesine ya da "
            "hata mesajındaki \"Bildir\"e dokunabilirsiniz."))
        self.page.update()

    def _new(self):
        self.state.router.push(report_form(self.state, context=report_context(self.state), on_sent=self.refresh))

    def _detail(self, r):
        page = self.page
        parts = [muted(f"{r['category_label']} · {r['status_label']} · {fmt_date(r['created_at'])}", size=12),
                 ft.Text(r["message"], selectable=True)]
        if r["attachments"]:
            names = ", ".join(a["original_name"] + (" (silindi)" if a["deleted_at"] else "") for a in r["attachments"])
            parts.append(muted(f"Ekler: {names}", size=12))
        if r["response"]:
            parts.append(card(ft.Column([ft.Text("Yanıt", weight=ft.FontWeight.W_600),
                                         ft.Text(r["response"], selectable=True)], spacing=4),
                              bgcolor=ft.Colors.PRIMARY_CONTAINER, padding=12))
        page.show_dialog(ft.AlertDialog(
            title=ft.Text("Bildirim"),
            content=ft.Container(ft.Column(parts, spacing=10, tight=True, scroll=ft.ScrollMode.AUTO), width=420),
            actions=[ft.TextButton("Kapat", on_click=lambda e: page.pop_dialog())],
        ))
