"""Small UI helpers shared by screens (formatting, inputs, form scaffold, error handling)."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import flet as ft

from services.api_client import ApiError, SessionExpired

from .choices import NONE


class FormError(Exception):
    """Client-side input error shown to the user."""


# ---------- formatting ----------
def fmt_money(value) -> str:
    text = f"{Decimal(str(value or 0)):,.2f}"  # 1,234.50
    return text.replace(",", "_").replace(".", ",").replace("_", ".") + " ₺"


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "-"
    y, m, d = iso[:10].split("-")
    return f"{d}.{m}.{y}"


def parse_money(text: str | None, allow_negative=False, allow_zero=False) -> str:
    """Turkish input: '1.234,50', '300.000', '1234,5' -> '1234.50' / '300000.00'. '1234.50' is also accepted."""
    raw = (text or "").strip().replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", raw):
        raw = raw.replace(".", "")  # dots are thousands separators
    try:
        value = Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise FormError("Geçerli bir tutar girin.")
    if (value == 0 and not allow_zero) or (value < 0 and not allow_negative):
        raise FormError("Tutar sıfırdan büyük olmalı.")
    return str(value)


def money_input_value(value) -> str:
    return "" if value in (None, "") else str(value).replace(".", ",")


# ---------- feedback ----------
def toast(page: ft.Page, message: str, error=False):
    page.show_dialog(ft.SnackBar(ft.Text(message), bgcolor=ft.Colors.RED_700 if error else None))


def guarded(page: ft.Page, fn):
    """Wrap an async action: show API/form errors as a snackbar instead of crashing."""

    async def handler(e=None):
        try:
            await fn()
        except SessionExpired:
            pass  # AppState already redirected to login
        except (ApiError, FormError) as err:
            toast(page, getattr(err, "message", str(err)), error=True)

    return handler


def confirm(page: ft.Page, message: str, on_yes):
    """Show a yes/no dialog; on_yes is an async callable."""

    async def yes(e):
        page.pop_dialog()
        await guarded(page, on_yes)()

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Emin misiniz?"),
            content=ft.Text(message),
            actions=[ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()), ft.TextButton("Evet", on_click=yes)],
        )
    )


# ---------- inputs ----------
def text_field(label, value="", **kwargs) -> ft.TextField:
    return ft.TextField(label=label, value=value or "", **kwargs)


def money_field(label, value=None) -> ft.TextField:
    return ft.TextField(label=label, value=money_input_value(value), keyboard_type=ft.KeyboardType.NUMBER)


def int_field(label, value=None) -> ft.TextField:
    return ft.TextField(label=label, value="" if value is None else str(value), keyboard_type=ft.KeyboardType.NUMBER)


def parse_int(field: ft.TextField, name: str, required=False, minimum=1) -> int | None:
    raw = (field.value or "").strip()
    if not raw:
        if required:
            raise FormError(f"{name} gerekli.")
        return None
    if not raw.isdigit() or int(raw) < minimum:
        raise FormError(f"{name} en az {minimum} olan bir tam sayı olmalı.")
    return int(raw)


def dropdown(label, options, value=None, with_none=False, none_text="Seçilmedi") -> ft.Dropdown:
    opts = ([(NONE, none_text)] if with_none else []) + list(options)
    if with_none and value is None:
        value = NONE
    return ft.Dropdown(
        label=label,
        value=value,
        options=[ft.DropdownOption(key=k, text=t) for k, t in opts],
    )


def dropdown_value(dd: ft.Dropdown):
    return None if dd.value in (None, NONE) else dd.value


class DateInput:
    """Read-only text field + date picker. `.iso` returns 'YYYY-MM-DD' or None."""

    def __init__(self, page: ft.Page, label: str, value: date | str | None = None, optional=False):
        self.page = page
        self.value = date.fromisoformat(value) if isinstance(value, str) else value
        self.text = ft.TextField(label=label, read_only=True, expand=True, value=self._display())
        self.picker = ft.DatePicker(
            value=datetime.combine(self.value, datetime.min.time()) if self.value else None,
            first_date=datetime(2000, 1, 1),
            last_date=datetime(2100, 12, 31),
            on_change=self._picked,
        )
        buttons = [ft.IconButton(ft.Icons.CALENDAR_MONTH, on_click=lambda e: page.show_dialog(self.picker))]
        if optional:
            buttons.append(ft.IconButton(ft.Icons.CLEAR, on_click=self._clear))
        self.control = ft.Row([self.text, *buttons])

    def _display(self):
        return self.value.strftime("%d.%m.%Y") if self.value else ""

    def _picked(self, e):
        picked = e.control.value
        self.value = picked.date() if isinstance(picked, datetime) else picked
        self.text.value = self._display()
        self.page.update()

    def _clear(self, e):
        self.value = None
        self.text.value = ""
        self.page.update()

    @property
    def iso(self) -> str | None:
        return self.value.isoformat() if self.value else None


# ---------- scaffolds ----------
def form_view(state, route, title, controls, on_save, on_delete=None, delete_message="Bu kayıt silinecek.") -> ft.View:
    """Standard form page: AppBar (+ delete), scrollable fields, save button."""
    page = state.page
    save_button = ft.FilledButton("Kaydet")

    async def save():
        save_button.disabled = True
        page.update()
        try:
            await on_save()
        finally:
            save_button.disabled = False
            page.update()

    save_button.on_click = guarded(page, save)
    actions = []
    if on_delete:
        actions.append(ft.IconButton(ft.Icons.DELETE, on_click=lambda e: confirm(page, delete_message, on_delete)))

    return ft.View(
        route=route,
        appbar=ft.AppBar(title=ft.Text(title), actions=actions),
        controls=[ft.Column([*controls, save_button], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)],
        padding=16,
    )


def empty_text(message: str) -> ft.Control:
    return ft.Container(ft.Text(message, color=ft.Colors.GREY_600), padding=24)
