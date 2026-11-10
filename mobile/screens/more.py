import flet as ft

from .autopay import AutoPaymentsScreen
from .choices import ACCOUNT_TYPES, KINDS, label
from .reports import ReportsScreen
from .settings import settings_view
from .statements import StatementsScreen
from .theme import EXPENSE, MUTED, card, grouped, icon_badge, muted, section
from .ui import (
    FormError, confirm, dropdown, empty_text, fmt_money, form_view, guarded, int_field, money_input_value,
    parse_int, parse_money, text_field,
)


class MoreTab:
    title = "Diğer"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.fab = None
        self.avatar = ft.Text(size=18, weight=ft.FontWeight.W_700, color=ft.Colors.ON_PRIMARY)
        self.user_name = ft.Text(size=16, weight=ft.FontWeight.W_600)
        self.user_email = muted("", size=13)
        push = self._push

        def item(icon, color, title, on_click, subtitle=None):
            return ft.ListTile(leading=icon_badge(icon, color, size=36), title=ft.Text(title, weight=ft.FontWeight.W_500),
                               subtitle=muted(subtitle) if subtitle else None,
                               trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=MUTED), on_click=on_click)

        self.control = ft.ListView(
            [
                card(ft.Row([
                    ft.Container(self.avatar, width=48, height=48, border_radius=24, bgcolor=ft.Colors.PRIMARY,
                                 alignment=ft.Alignment.CENTER),
                    ft.Column([self.user_name, self.user_email], spacing=2, expand=True),
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Profili düzenle",
                                  on_click=lambda e: push(profile_form(state, on_saved=self.refresh))),
                ], spacing=14)),
                section("Para"),
                *grouped([
                    item(ft.Icons.ACCOUNT_BALANCE, "#0F766E", "Hesaplar", lambda e: push(AccountsScreen(state).view),
                         "Banka / nakit, kart kesim günü"),
                    item(ft.Icons.AUTORENEW, "#0EA5E9", "Otomatik ödemelerim",
                         lambda e: push(AutoPaymentsScreen(state).view), "Düzenli ve taksitli ödemeler"),
                    item(ft.Icons.UPLOAD_FILE, "#1D4ED8", "Ekstreler", lambda e: push(StatementsScreen(state).view),
                         "Yüklenen hesap / kart ekstreleri"),
                    item(ft.Icons.INSIGHTS, "#7C3AED", "Raporlar", lambda e: push(ReportsScreen(state).view),
                         "Kategori, trend, net varlık, portföy"),
                ]),
                section("Ayarlar"),
                *grouped([
                    item(ft.Icons.TUNE, "#475569", "Uygulama ayarları",
                         lambda e: push(settings_view(state, self._settings_changed)),
                         "Tema, varsayılan hesap, açılış ekranı"),
                    item(ft.Icons.CATEGORY, "#D97706", "Kategoriler", lambda e: push(CategoriesScreen(state).view)),
                    item(ft.Icons.AUTO_FIX_HIGH, "#DB2777", "Öğrenilen kategoriler",
                         lambda e: push(CategoryRulesScreen(state).view), "İşyeri → kategori eşleştirmeleri"),
                ]),
                *grouped([
                    ft.ListTile(leading=icon_badge(ft.Icons.LOGOUT, "#DC2626", size=36),
                                title=ft.Text("Çıkış yap", color=EXPENSE, weight=ft.FontWeight.W_500),
                                on_click=lambda e: confirm(self.page, "Oturumunuz kapatılacak.", state.logout)),
                ]),
            ],
            expand=True,
            spacing=12,
            padding=ft.Padding.only(left=16, right=16, top=4, bottom=96),
        )

    def _push(self, view):
        self.state.router.push(view)

    async def _settings_changed(self):
        """Home tabs read settings on refresh; nothing to rebuild here."""

    async def refresh(self):
        u = self.state.user or {}
        full_name = " ".join(filter(None, [u.get("first_name"), u.get("last_name")]))
        name = full_name or u.get("username", "")
        self.avatar.value = (name[:1] or "?").upper()
        self.user_name.value = name
        self.user_email.value = u.get("email", "")
        self.page.update()


# ---------- accounts ----------
class AccountsScreen:
    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True, padding=16, spacing=12)
        self.view = ft.View(
            route="/accounts",
            appbar=ft.AppBar(title=ft.Text("Hesaplar")),
            floating_action_button=ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda e: self._open(None)),
            controls=[self.list],
        )
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        await self.state.load_refs()
        self.list.controls = grouped([
            ft.ListTile(
                leading=icon_badge(ft.Icons.ACCOUNT_BALANCE if a["account_type"] == "bank" else ft.Icons.PAYMENTS,
                                   "#94A3B8" if a["is_archived"] else "#0F766E", size=36),
                title=ft.Text(a["name"] + (" (arşiv)" if a["is_archived"] else ""), weight=ft.FontWeight.W_500),
                subtitle=ft.Text(" · ".join(filter(None, [
                    label(ACCOUNT_TYPES, a["account_type"]),
                    a.get("card_name") or "",
                    f"kesim günü {a['statement_day']}" if a["statement_day"] else "",
                ]))),
                trailing=ft.Text(fmt_money(a["balance"]), weight=ft.FontWeight.W_600),
                on_click=lambda e, a=a: self._open(a),
            )
            for a in self.state.accounts
        ], empty_text("Henüz hesap yok."))
        self.page.update()

    def _open(self, account):
        self.state.router.push(account_form(self.state, account, on_saved=self.refresh))


def account_form(state, a: dict | None, on_saved) -> ft.View:
    a = a or {}
    is_edit = bool(a.get("id"))
    name = text_field("Ad", a.get("name"))
    account_type = dropdown("Tür", ACCOUNT_TYPES, a.get("account_type", "bank"))
    opening = ft.TextField(
        label="Açılış bakiyesi (bugünkü bakiye)",
        value=money_input_value(a.get("opening_balance", "0")),
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    statement_day = int_field("Kredi kartı ekstre kesim günü (1-31, kart yoksa boş)", a.get("statement_day"))
    card_name = text_field("Kart adı (ör. Enpara Kredi Kartı)", a.get("card_name"))
    archived = ft.Switch(label="Arşivlendi", value=a.get("is_archived", False))

    async def save():
        if not name.value:
            raise FormError("Ad gerekli.")
        opening_value = parse_money(opening.value or "0", allow_negative=True, allow_zero=True)
        day = parse_int(statement_day, "Kesim günü")
        if day is not None and day > 31:
            raise FormError("Kesim günü 1 ile 31 arasında olmalı.")
        payload = {
            "name": name.value,
            "account_type": account_type.value,
            "opening_balance": opening_value,
            "statement_day": day,
            "card_name": card_name.value,
            "is_archived": archived.value,
        }
        if is_edit:
            await state.budget.accounts.update(a["id"], payload)
        else:
            await state.budget.accounts.create(payload)
        state.router.pop()
        await on_saved()

    async def delete():
        await state.budget.accounts.delete(a["id"])
        state.router.pop()
        await on_saved()

    return form_view(
        state, "/account", "Hesabı düzenle" if is_edit else "Yeni hesap",
        [name, account_type, opening, statement_day, card_name,
         ft.Text("Kart harcamaları aylık özette ekstre dönemine göre sayılır (ör. kesim 15 → 16 Ocak-15 Şubat "
                 "harcamaları Şubat'a). Kart ekstresi yüklenince boşsa otomatik doldurulur.",
                 size=12, color=MUTED)] + ([archived] if is_edit else []),
        on_save=save, on_delete=delete if is_edit else None,
    )


# ---------- categories ----------
class CategoriesScreen:
    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True, padding=16, spacing=12)
        self.view = ft.View(
            route="/categories",
            appbar=ft.AppBar(title=ft.Text("Kategoriler")),
            floating_action_button=ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda e: self._open(None)),
            controls=[self.list],
        )
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        await self.state.load_refs()
        controls = []
        for kind, kind_label in KINDS:
            controls.append(section(kind_label))
            controls += grouped([
                ft.ListTile(
                    title=ft.Text(c["name"] + (" (arşiv)" if c["is_archived"] else ""),
                                  color=MUTED if c["is_archived"] else None),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=MUTED),
                    on_click=lambda e, c=c: self._open(c),
                )
                for c in self.state.categories
                if c["kind"] == kind
            ])
        self.list.controls = controls
        self.page.update()

    def _open(self, category):
        self.state.router.push(category_form(self.state, category, on_saved=self.refresh))


def category_form(state, c: dict | None, on_saved) -> ft.View:
    c = c or {}
    is_edit = bool(c.get("id"))
    name = text_field("Ad", c.get("name"))
    kind = dropdown("Tür", KINDS, c.get("kind", "expense"))
    archived = ft.Switch(label="Arşivlendi", value=c.get("is_archived", False))

    async def save():
        if not name.value:
            raise FormError("Ad gerekli.")
        payload = {"name": name.value, "kind": kind.value, "is_archived": archived.value}
        if is_edit:
            await state.budget.categories.update(c["id"], payload)
        else:
            await state.budget.categories.create(payload)
        state.router.pop()
        await on_saved()

    async def delete():
        await state.budget.categories.delete(c["id"])
        state.router.pop()
        await on_saved()

    return form_view(
        state, "/category", "Kategoriyi düzenle" if is_edit else "Yeni kategori",
        [name, kind] + ([archived] if is_edit else []),
        on_save=save, on_delete=delete if is_edit else None,
        delete_message="Kategori silinecek; bu kategorideki işlemler kategorisiz kalır.",
    )


# ---------- learned category rules ----------
class CategoryRulesScreen:
    """Merchant -> category rules learned from the user's choices; delete wrong ones."""

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True, padding=16, spacing=12)
        self.view = ft.View(route="/category-rules", appbar=ft.AppBar(title=ft.Text("Öğrenilen kategoriler")),
                            controls=[self.list])
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        rules = await self.state.budget.category_rules.list()
        self.list.controls = grouped([
            ft.ListTile(
                title=ft.Text(r["merchant_key"], weight=ft.FontWeight.W_500),
                subtitle=ft.Text(f"{r['category_name']} · {label(KINDS, r['kind'])} · {r['hits']} kez uygulandı"),
                trailing=ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=lambda e, r=r: confirm(
                    self.page, f"'{r['merchant_key']}' eşleştirmesi silinecek.", lambda: self._delete(r))),
            )
            for r in rules
        ], empty_text("Henüz öğrenilen eşleştirme yok. Ekstre önizlemesinde veya bir kayıtta kategori "
                         "değiştirdiğinizde burada görünür."))
        self.page.update()

    async def _delete(self, rule):
        await self.state.budget.category_rules.delete(rule["id"])
        await self.refresh()


# ---------- profile ----------
def profile_form(state, on_saved) -> ft.View:
    u = state.user or {}
    info = ft.Text(f"Kullanıcı adı: {u.get('username', '')}\nE-posta: {u.get('email', '')}")
    first_name = text_field("Ad", u.get("first_name"))
    last_name = text_field("Soyad", u.get("last_name"))

    async def save():
        state.user = await state.auth.update_me(first_name=first_name.value, last_name=last_name.value)
        state.router.pop()
        await on_saved()

    return form_view(state, "/profile", "Profil", [info, first_name, last_name], on_save=save)
