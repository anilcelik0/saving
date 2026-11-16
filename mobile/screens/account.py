"""
Account lifecycle in the app: freeze / delete (password + confirmation) and the screen shown when a frozen or
deletion-pending account logs in (reopen / cancel deletion).
"""

import flet as ft

from .form_kit import QuickForm, field
from .theme import EXPENSE, card, icon_badge, muted
from .ui import FormError, fmt_date, guarded

MODES = {
    "deactivate": {
        "title": "Hesabı dondur", "icon": (ft.Icons.PAUSE_CIRCLE, "#475569"), "action": "Hesabımı dondur",
        "points": [
            "Tüm cihazlarda oturumun kapanır.",
            "Verilerin silinmez, olduğu gibi saklanır.",
            "İstediğin zaman tekrar giriş yapıp hesabını yeniden açabilirsin.",
        ],
        "confirm": "Hesabımın dondurulacağını anladım.",
    },
    "delete": {
        "title": "Hesabı sil", "icon": (ft.Icons.DELETE_FOREVER, "#DC2626"), "action": "Hesabımı sil",
        "points": [
            "Hesabın hemen kilitlenir ve tüm cihazlarda oturumun kapanır.",
            "30 gün içinde tekrar giriş yaparak silmeyi iptal edebilirsin.",
            "30 gün sonra hesabın ve tüm verilerin (hesaplar, gelir/gider kayıtları, ekstreler, yatırımlar, "
            "bildirimler) kalıcı olarak silinir. Bu işlem geri alınamaz.",
        ],
        "confirm": "Hesabımın ve tüm verilerimin 30 gün sonra kalıcı olarak silineceğini anladım.",
    },
}


def _points(lines):
    return ft.Column([ft.Row([ft.Text("•", size=14), ft.Text(line, size=14, expand=True)],
                             vertical_alignment=ft.CrossAxisAlignment.START, spacing=8) for line in lines], spacing=8)


def close_account_form(state, mode: str) -> ft.View:
    """mode: "deactivate" (freeze) or "delete" (deletion after 30 days)."""
    cfg = MODES[mode]
    password = ft.TextField(label="Şifren", password=True, can_reveal_password=True)
    confirm = ft.Checkbox(value=False)
    icon, color = cfg["icon"]

    async def save():
        if not confirm.value:
            raise FormError("Devam etmek için onay kutusunu işaretleyin.")
        if not password.value:
            raise FormError("Onaylamak için şifrenizi girin.")
        if mode == "delete":
            user = await state.auth.request_deletion(password.value)
            message = (f"Silme talebin alındı. Hesabın {fmt_date(user['delete_after'])} tarihinde silinecek; "
                       "bu tarihe kadar giriş yaparak iptal edebilirsin.")
        else:
            await state.auth.deactivate(password.value)
            message = "Hesabın donduruldu. Tekrar giriş yaparak yeniden açabilirsin."
        await state.end_session(message)

    body = [
        ft.Row([icon_badge(icon, color, size=56)]),
        card(_points(cfg["points"])),
        field("Onaylamak için şifreni gir", password),
        ft.Row([confirm, ft.Container(ft.Text(cfg["confirm"], size=13), expand=True, padding=ft.Padding.only(top=10))],
               vertical_alignment=ft.CrossAxisAlignment.START, spacing=4),
    ]
    form = QuickForm(state, f"/account/{mode}", body, on_save=save, title=cfg["title"], action_text=cfg["action"])
    if mode == "delete":
        form.button.bgcolor = ft.Colors.ERROR
        form.button.color = ft.Colors.ON_ERROR
    return form.view


def account_status_view(state, on_reopened) -> ft.View:
    """Shown instead of the app after logging in with a frozen / deletion-pending account."""
    page = state.page
    user = state.user or {}
    deletion = user.get("account_status") == "deletion_pending"
    if deletion:
        title = "Hesabın silinmek üzere"
        text = (f"Silme talebin üzerine hesabın kilitlendi. {fmt_date(user.get('delete_after'))} tarihinde tüm "
                "verilerinle birlikte kalıcı olarak silinecek. Vazgeçtiysen silmeyi iptal edip devam edebilirsin.")
        badge = icon_badge(ft.Icons.DELETE_FOREVER, "#DC2626", size=56)
        action = "Silmeyi iptal et ve devam et"
    else:
        title = "Hesabın dondurulmuş"
        text = "Verilerin korunuyor. Uygulamayı kullanmaya devam etmek için hesabını yeniden aç."
        badge = icon_badge(ft.Icons.PAUSE_CIRCLE, "#475569", size=56)
        action = "Hesabımı yeniden aç"
    button = ft.FilledButton(action, height=52, expand=True)

    async def reopen():
        button.disabled = True
        page.update()
        try:
            state.user = await state.auth.reactivate()
            await on_reopened()
        finally:
            button.disabled = False
            page.update()

    button.on_click = guarded(page, reopen)
    return ft.View(
        route="/account-status",
        padding=0,
        bgcolor=ft.Colors.SURFACE,
        controls=[ft.SafeArea(ft.Column([
            ft.ListView([
                ft.Container(height=24),
                ft.Row([badge]),
                ft.Text(title, size=24, weight=ft.FontWeight.W_800),
                muted(text, size=15, color=EXPENSE if deletion else None),
            ], spacing=12, expand=True, padding=ft.Padding.symmetric(horizontal=24)),
            ft.Container(ft.Column([
                ft.Row([button]),
                ft.TextButton("Çıkış yap", on_click=lambda e: page.run_task(state.logout)),
            ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.only(left=24, right=24, top=8, bottom=16)),
        ], spacing=0, expand=True), expand=True)],
    )
