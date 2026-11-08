import flet as ft

from .ui import FormError, guarded, text_field


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

    async def submit():
        if password.value != password2.value:
            raise FormError("Şifreler eşleşmiyor.")
        await state.register(
            username=username.value,
            email=email.value,
            password=password.value,
            first_name=first_name.value,
            last_name=last_name.value,
        )

    return ft.View(
        route="/register",
        appbar=ft.AppBar(title=ft.Text("Kayıt ol")),
        padding=16,
        controls=[
            ft.Column(
                [username, email, password, password2, first_name, last_name,
                 ft.FilledButton("Kayıt ol", on_click=guarded(page, submit))],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
        ],
    )
