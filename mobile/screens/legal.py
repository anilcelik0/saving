"""
Legal documents (privacy policy, KVKK notice): reader, acceptance checkboxes (register screen and the gate shown
when a new version is published) and Diğer > Gizlilik ve KVKK (accepted versions, dates).
"""

import flet as ft

from .theme import ACCENT, CARD, INCOME, MUTED, card, grouped, icon_badge, muted
from .ui import empty_text, fmt_date, guarded

# the KVKK notice is information (acknowledged), the privacy policy is accepted
CHECK_TEXT = {"kvkk": "Okudum, bilgilendirildim."}
DEFAULT_CHECK_TEXT = "Okudum, kabul ediyorum."
ICONS = {"privacy": (ft.Icons.PRIVACY_TIP, "#0F766E"), "kvkk": (ft.Icons.GAVEL, "#6366F1")}


def _badge(kind, size=36):
    icon, color = ICONS.get(kind, (ft.Icons.DESCRIPTION, "#64748B"))
    return icon_badge(icon, color, size=size)


def document_view(state, kind: str, title: str = "") -> ft.View:
    """Reads the current version of a document (works without a session, e.g. from the register screen)."""
    page = state.page
    header = ft.Text(title, size=22, weight=ft.FontWeight.W_700)
    meta = muted("", size=13)
    body = ft.Column([ft.ProgressRing(width=24, height=24)], spacing=0)

    async def load():
        doc = await state.auth.legal_document(kind)
        header.value = doc["title"]
        meta.value = f"Sürüm {doc['version']} · Yürürlük tarihi {fmt_date(doc['published_at'])}"
        body.controls = [ft.Markdown(doc["body"], selectable=True,
                                     extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED)]
        page.update()

    page.run_task(guarded(page, load))
    return ft.View(
        route=f"/legal/{kind}",
        appbar=ft.AppBar(),
        padding=0,
        controls=[ft.ListView([header, meta, ft.Container(height=8), body], expand=True, spacing=4,
                              padding=ft.Padding.only(left=20, right=20, bottom=32))],
    )


class AcceptanceList:
    """Documents with a checkbox each (title opens the text). `.all_checked`, `.ids` (checked documents)."""

    def __init__(self, state, documents: list[dict], on_change=None):
        self.on_change = on_change
        self.boxes = {}
        rows = []
        for d in documents:
            read = ft.Container(
                ft.Text(d["title"], weight=ft.FontWeight.W_600, color=ACCENT,
                        style=ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)),
                on_click=lambda e, d=d: state.router.push(document_view(state, d["kind"], d["title"])),
            )
            if d.get("requires_acceptance", True):
                box = ft.Checkbox(value=False, on_change=self._changed)
                self.boxes[d["id"]] = box
                text = muted(CHECK_TEXT.get(d["kind"], DEFAULT_CHECK_TEXT), size=13)
                rows.append(ft.Row([box, ft.Column([read, text], spacing=2, expand=True)],
                                   vertical_alignment=ft.CrossAxisAlignment.START, spacing=4))
            else:
                rows.append(ft.Row([ft.Container(width=40), read]))
        self.control = ft.Column(rows, spacing=12)

    def _changed(self, e):
        if self.on_change:
            self.on_change()

    @property
    def all_checked(self) -> bool:
        return all(box.value for box in self.boxes.values())

    @property
    def ids(self) -> list[str]:
        return [doc_id for doc_id, box in self.boxes.items() if box.value]


def consent_gate_view(state, pending: list[dict], on_done) -> ft.View:
    """Shown instead of the app until the current (new) versions are accepted. on_done: async callable."""
    page = state.page
    updated = any(d["version"] > 1 for d in pending)
    button = ft.FilledButton("Onayla ve devam et", disabled=True, height=52, expand=True)

    def refresh():
        button.disabled = not acceptance.all_checked
        page.update()

    acceptance = AcceptanceList(state, pending, on_change=refresh)

    async def submit():
        button.disabled = True
        page.update()
        try:
            await state.auth.accept(acceptance.ids)
            await on_done()
        finally:
            button.disabled = not acceptance.all_checked
            page.update()

    button.on_click = guarded(page, submit)
    title = "Metinlerimiz güncellendi" if updated else "Devam etmeden önce"
    text = ("Aşağıdaki metinlerin yeni sürümleri yayınlandı. Uygulamayı kullanmaya devam etmek için okuyup "
            "onaylamanız gerekiyor." if updated else
            "Uygulamayı kullanabilmek için aşağıdaki metinleri okuyup onaylamanız gerekiyor.")
    return ft.View(
        route="/consent",
        padding=0,
        bgcolor=ft.Colors.SURFACE,
        controls=[ft.SafeArea(ft.Column([
            ft.ListView([
                ft.Container(height=24),
                ft.Row([icon_badge(ft.Icons.PRIVACY_TIP, "#0F766E", size=56)]),  # Row: keep the badge's size
                ft.Text(title, size=24, weight=ft.FontWeight.W_800),
                muted(text, size=15),
                ft.Container(height=8),
                card(acceptance.control),
            ], spacing=12, expand=True, padding=ft.Padding.symmetric(horizontal=24)),
            ft.Container(ft.Column([
                ft.Row([button]),
                ft.TextButton("Çıkış yap", on_click=lambda e: page.run_task(state.logout)),
            ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.only(left=24, right=24, top=8, bottom=16)),
        ], spacing=0, expand=True), expand=True)],
    )


class LegalSettingsScreen:
    """Diğer > Gizlilik ve KVKK: current texts, accepted version and date, how to use KVKK rights."""

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True, padding=16, spacing=12)
        self.view = ft.View(route="/legal", appbar=ft.AppBar(title=ft.Text("Gizlilik ve KVKK")),
                            controls=[self.list], padding=0)
        self.view.data = self  # refreshed after every change (AppState.data_changed)
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        data = await self.state.auth.consents()
        rows = []
        for d in data["documents"]:
            if d["is_accepted"]:
                status, color = f"Onaylandı · sürüm {d['version']} · {fmt_date(d['accepted_at'])}", INCOME
            elif d["accepted_version"]:
                status, color = f"Sürüm {d['version']} onay bekliyor (onaylı: sürüm {d['accepted_version']})", None
            elif d["requires_acceptance"]:
                status, color = f"Sürüm {d['version']} onay bekliyor", None
            else:
                status, color = f"Sürüm {d['version']}", None
            rows.append(ft.ListTile(
                leading=_badge(d["kind"]),
                title=ft.Text(d["title"], weight=ft.FontWeight.W_500),
                subtitle=muted(status, color=color or MUTED),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=MUTED),
                on_click=lambda e, d=d: self.state.router.push(document_view(self.state, d["kind"], d["title"])),
            ))
        controls = grouped(rows, empty_text("Yayınlanmış metin yok."))
        if data["pending"]:
            controls.append(ft.FilledButton("Bekleyen metinleri onayla", on_click=lambda e: self._open_gate(data)))
        controls.append(card(ft.Column([
            ft.Text("Haklarınız", weight=ft.FontWeight.W_600),
            muted("KVKK kapsamındaki haklarınızı (bilgi talebi, düzeltme, silme vb.) kullanmak için KVKK Aydınlatma "
                  "Metni'ndeki iletişim adresine, uygulamada kayıtlı e-posta adresinizden yazabilirsiniz.", size=13),
            muted("Metinler güncellendiğinde uygulama yeni sürümü gösterir ve devam etmeden önce onayınızı ister.",
                  size=13),
        ], spacing=6), bgcolor=CARD))
        self.list.controls = controls
        self.page.update()

    def _open_gate(self, data):
        async def done():
            self.state.router.pop()
            await self.refresh()

        self.state.router.push(consent_gate_view(self.state, data["pending"], done))
