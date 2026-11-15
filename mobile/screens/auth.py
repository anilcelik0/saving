import flet as ft

from .legal import AcceptanceList, document_view
from .ui import FormError, guarded, text_field


def _legal_links(state) -> ft.Row:
    def link(kind, title):
        return ft.TextButton(title, on_click=lambda e: state.router.push(document_view(state, kind, title)))

    return ft.Row([link("privacy", "Gizlilik Politikası"), link("kvkk", "KVKK Aydınlatma Metni")],
                  alignment=ft.MainAxisAlignment.CENTER, wrap=True)


def login_view(state) -> ft.View:
    page = state.page
    identifier = text_field("Kullanıcı adı veya e-posta", autofocus=True)
    password = ft.TextField(label="Şifre", password=True, can_reveal_password=True)

    async def submit():
        if not identifier.value or not password.value:
            raise FormError("Kullanıcı adı/e-posta ve şifre gerekli.")
        await state.login(identifier.value, password.value)

    handler = guarded(page, submit)
    password.on_submit = handler

    return ft.View(
        route="/login",
        padding=24,
        vertical_alignment=ft.MainAxisAlignment.CENTER,
        controls=[
            ft.Text("Saving", size=28, weight=ft.FontWeight.BOLD),
            identifier,
            password,
            ft.FilledButton("Giriş yap", on_click=handler),
            ft.TextButton("Hesabın yok mu? Kayıt ol", on_click=lambda e: state.router.push(register_view(state))),
            _legal_links(state),
        ],
    )


def register_view(state) -> ft.View:
    page = state.page
    username = text_field("Kullanıcı adı")
    email = text_field("E-posta", keyboard_type=ft.KeyboardType.EMAIL)
    password = ft.TextField(label="Şifre", password=True, can_reveal_password=True)
    password2 = ft.TextField(label="Şifre (tekrar)", password=True, can_reveal_password=True)
    first_name = text_field("Ad (opsiyonel)")
    last_name = text_field("Soyad (opsiyonel)")
    legal_box = ft.Column([ft.ProgressRing(width=20, height=20)])
    current = {"acceptance": None}

    async def load_documents():
        docs = await state.auth.legal_documents()
        current["acceptance"] = AcceptanceList(state, docs) if docs else None
        legal_box.controls = [current["acceptance"].control] if docs else []
        page.update()

    async def submit():
        if password.value != password2.value:
            raise FormError("Şifreler eşleşmiyor.")
        acceptance = current["acceptance"]
        if acceptance and not acceptance.all_checked:
            raise FormError("Kayıt olmak için metinleri okuyup onaylayın.")
        await state.register(
            username=username.value,
            email=email.value,
            password=password.value,
            first_name=first_name.value,
            last_name=last_name.value,
            accepted_documents=acceptance.ids if acceptance else [],
        )

    page.run_task(guarded(page, load_documents))
    return ft.View(
        route="/register",
        appbar=ft.AppBar(title=ft.Text("Kayıt ol")),
        padding=16,
        controls=[
            ft.Column(
                [username, email, password, password2, first_name, last_name, legal_box,
                 ft.FilledButton("Kayıt ol", on_click=guarded(page, submit))],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
        ],
    )
