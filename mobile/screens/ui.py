"""Small UI helpers shared by screens (formatting, inputs, error handling). Form style: form_kit.py."""

import re
from decimal import Decimal, InvalidOperation

import flet as ft

from services.api_client import ApiError, SessionExpired

from .choices import NONE
from .theme import MUTED


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


def fmt_number(value, max_decimals=2) -> str:
    """Turkish format, trailing zeros trimmed: 1234.5000 -> '1.234,5', 10.000000 -> '10'."""
    number = Decimal(str(value or 0)).quantize(Decimal(1).scaleb(-max_decimals))
    text = f"{number:,.{max_decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return text.rstrip("0").rstrip(",") if "," in text else text


def fmt_pct(value) -> str:
    if value in (None, ""):
        return "-"
    number = Decimal(str(value))
    return ("+" if number > 0 else "") + fmt_number(number) + "%"


def parse_decimal(text: str | None, name: str, decimals: int = 2, allow_zero=False) -> str:
    """'1,5' / '1.250,75' / '10' -> '1.5' / '1250.75' / '10'; at most `decimals` decimal places."""
    raw = (text or "").strip().replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw) and decimals < 3:
        raw = raw.replace(".", "")  # dots are thousands separators
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise FormError(f"{name} için geçerli bir sayı girin.")
    if value < 0 or (value == 0 and not allow_zero):
        raise FormError(f"{name} sıfırdan büyük olmalı.")
    if -value.normalize().as_tuple().exponent > decimals:
        raise FormError(f"{name} en fazla {decimals} ondalık basamak olabilir." if decimals else f"{name} tam sayı olmalı.")
    return f"{value.normalize():f}"


def money_input_value(value) -> str:
    return "" if value in (None, "") else str(value).replace(".", ",")


# ---------- feedback ----------
def toast(page: ft.Page, message: str, error=False):
    page.show_dialog(ft.SnackBar(ft.Text(message), bgcolor=ft.Colors.ERROR if error else None))


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


def ask_scope(page: ft.Page, title: str, action, following_text="Bu ve sonraki bekleyenler"):
    """For series occurrences: run action('this') or action('following')."""

    def run(scope):
        async def handler(e):
            page.pop_dialog()
            await guarded(page, lambda: action(scope))()
        return handler

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text(title),
            actions=[
                ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()),
                ft.TextButton("Sadece bu kayıt", on_click=run("this")),
                ft.TextButton(following_text, on_click=run("following")),
            ],
        )
    )


# ---------- inputs ----------
def text_field(label, value="", **kwargs) -> ft.TextField:
    return ft.TextField(label=label, value=value or "", **kwargs)


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


def empty_text(message: str) -> ft.Control:
    return ft.Container(ft.Text(message, color=MUTED), padding=24)
