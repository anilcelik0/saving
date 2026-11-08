import flet as ft

from .choices import ACCOUNT_TYPES, KINDS, label
from .plans import PlansScreen
from .ui import (
    FormError, confirm, dropdown, empty_text, fmt_money, form_view, guarded, money_input_value,
    parse_money, text_field,
)


class MoreTab:
    title = "Diğer"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.user_text = ft.Text()
        self.fab = None
        self.control = ft.ListView(
            [
                ft.Container(self.user_text, padding=16),
                ft.ListTile(leading=ft.Icon(ft.Icons.ACCOUNT_BALANCE), title=ft.Text("Hesaplar"),
                            on_click=lambda e: self._push(AccountsScreen(state).view)),
                ft.ListTile(leading=ft.Icon(ft.Icons.EVENT_REPEAT), title=ft.Text("Ödeme Planları"),
                            subtitle=ft.Text("Tüm düzenli ve taksitli planlar (bitenler dahil)"),
                            on_click=lambda e: self._push(PlansScreen(state).view)),
                ft.ListTile(leading=ft.Icon(ft.Icons.CATEGORY), title=ft.Text("Kategoriler"),
                            on_click=lambda e: self._push(CategoriesScreen(state).view)),
                ft.ListTile(leading=ft.Icon(ft.Icons.PERSON), title=ft.Text("Profil"),
                            on_click=lambda e: self._push(profile_form(state, on_saved=self.refresh))),
                ft.ListTile(leading=ft.Icon(ft.Icons.LOGOUT), title=ft.Text("Çıkış yap"),
                            on_click=lambda e: confirm(self.page, "Oturumunuz kapatılacak.", state.logout)),
            ],
            expand=True,
        )

    def _push(self, view):
        self.state.router.push(view)

    async def refresh(self):
        u = self.state.user or {}
        full_name = " ".join(filter(None, [u.get("first_name"), u.get("last_name")]))
        self.user_text.value = f"{full_name or u.get('username', '')}\n{u.get('email', '')}"
        self.page.update()


# ---------- accounts ----------
class AccountsScreen:
    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True)
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
        self.list.controls = [
            ft.ListTile(
                title=ft.Text(a["name"] + (" (arşiv)" if a["is_archived"] else "")),
                subtitle=ft.Text(label(ACCOUNT_TYPES, a["account_type"])),
                trailing=ft.Text(fmt_money(a["balance"])),
                on_click=lambda e, a=a: self._open(a),
            )
            for a in self.state.accounts
        ] or [empty_text("Henüz hesap yok.")]
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
    archived = ft.Switch(label="Arşivlendi", value=a.get("is_archived", False))

    async def save():
        if not name.value:
            raise FormError("Ad gerekli.")
        opening_value = parse_money(opening.value or "0", allow_negative=True, allow_zero=True)
        payload = {
            "name": name.value,
            "account_type": account_type.value,
            "opening_balance": opening_value,
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
        [name, account_type, opening] + ([archived] if is_edit else []),
        on_save=save, on_delete=delete if is_edit else None,
    )


# ---------- categories ----------
class CategoriesScreen:
    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True)
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
            controls.append(ft.Container(ft.Text(kind_label, weight=ft.FontWeight.BOLD), padding=ft.Padding.only(left=16, top=12)))
            controls += [
                ft.ListTile(
                    title=ft.Text(c["name"] + (" (arşiv)" if c["is_archived"] else "")),
                    on_click=lambda e, c=c: self._open(c),
                )
                for c in self.state.categories
                if c["kind"] == kind
            ]
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
