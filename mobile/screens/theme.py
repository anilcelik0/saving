"""
Design system (direction A, "calm & airy"): light/dark color schemes following the phone, plus shared building blocks
(cards, section headers, stats) and simple charts drawn with flet.canvas / containers (no extra dependency).

Screens use color ROLES (ft.Colors.PRIMARY, SURFACE_CONTAINER_LOWEST...) so both themes work without branching:
  CARD = card background · MUTED = secondary text · INCOME / EXPENSE = money colors · TRACK = empty bar/ring.
"""

import math
from decimal import Decimal
from pathlib import Path

import flet as ft
import flet.canvas as cv

from config import is_packaged

FONT = "Inter"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf"
FONT_ASSET = "fonts/Inter.ttf"  # bundled copy (assets/fonts/Inter.ttf): offline, no request to a third party
_HAS_ASSET = (Path(__file__).resolve().parent.parent / "assets" / FONT_ASSET).exists()
# a built app never downloads the font (privacy policy: no third-party requests) -> system font if not bundled
FONT_SRC = FONT_ASSET if _HAS_ASSET else (None if is_packaged() else FONT_URL)

LIGHT = ft.ColorScheme(
    primary="#0F766E", on_primary="#FFFFFF", primary_container="#CCFBF1", on_primary_container="#134E4A",
    secondary="#475569", on_secondary="#FFFFFF", secondary_container="#E2E8F0", on_secondary_container="#0F172A",
    tertiary="#15803D", on_tertiary="#FFFFFF", tertiary_container="#DCFCE7", on_tertiary_container="#14532D",
    error="#B91C1C", on_error="#FFFFFF", error_container="#FEE2E2", on_error_container="#7F1D1D",
    surface="#F6F7F9", on_surface="#0F172A", on_surface_variant="#475569",
    surface_container_lowest="#FFFFFF", surface_container_low="#F1F5F9", surface_container="#EDF1F5",
    surface_container_high="#E2E8F0", surface_container_highest="#CBD5E1",
    outline="#94A3B8", outline_variant="#E2E8F0", surface_tint="#00000000",
)
DARK = ft.ColorScheme(
    primary="#2DD4BF", on_primary="#042F2E", primary_container="#134E4A", on_primary_container="#CCFBF1",
    secondary="#9AA4B2", on_secondary="#0E1116", secondary_container="#2A313C", on_secondary_container="#E6EAF0",
    tertiary="#4ADE80", on_tertiary="#052E16", tertiary_container="#12301C", on_tertiary_container="#BBF7D0",
    error="#F87171", on_error="#450A0A", error_container="#3B1515", on_error_container="#FECACA",
    surface="#0E1116", on_surface="#E6EAF0", on_surface_variant="#9AA4B2",
    surface_container_lowest="#171B22", surface_container_low="#1C2129", surface_container="#222832",
    surface_container_high="#2A313C", surface_container_highest="#3A4350",
    outline="#5B6676", outline_variant="#2A313C", surface_tint="#00000000",
)

CARD = ft.Colors.SURFACE_CONTAINER_LOWEST
MUTED = ft.Colors.ON_SURFACE_VARIANT
INCOME = ft.Colors.TERTIARY
EXPENSE = ft.Colors.ERROR
TRACK = ft.Colors.SURFACE_CONTAINER_HIGH
ACCENT = ft.Colors.PRIMARY
# category / series colors: mid tones readable on both themes
CHART = ["#14B8A6", "#F59E0B", "#6366F1", "#EC4899", "#0EA5E9", "#84CC16", "#A855F7", "#94A3B8"]
INCOME_BAR, EXPENSE_BAR = "#14B8A6", "#FDBA74"


def _theme(scheme: ft.ColorScheme) -> ft.Theme:
    shape = ft.RoundedRectangleBorder(radius=14)
    return ft.Theme(
        color_scheme=scheme,
        font_family=FONT,
        use_material3=True,
        appbar_theme=ft.AppBarTheme(bgcolor=scheme.surface, center_title=False, elevation=0,
                                    title_text_style=ft.TextStyle(size=20, weight=ft.FontWeight.W_700,
                                                                  color=scheme.on_surface)),
        filled_button_theme=ft.FilledButtonTheme(style=ft.ButtonStyle(shape=shape, padding=ft.Padding.symmetric(horizontal=16, vertical=14))),
        outlined_button_theme=ft.OutlinedButtonTheme(style=ft.ButtonStyle(shape=shape, padding=ft.Padding.symmetric(horizontal=16, vertical=14))),
        input_decoration_theme=ft.InputDecorationTheme(
            filled=True, fill_color=scheme.surface_container_lowest,
            border=ft.OutlineInputBorder(side=ft.BorderSide(1, scheme.outline_variant), border_radius=14)),
        list_tile_theme=ft.ListTileTheme(shape=shape),
        divider_theme=ft.DividerTheme(color=scheme.outline_variant, thickness=1, space=1),
    )


THEME_MODES = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}


def apply_theme(page: ft.Page, mode: str = "system"):
    page.fonts = {FONT: FONT_SRC} if FONT_SRC else {}
    page.theme = _theme(LIGHT)
    page.dark_theme = _theme(DARK)
    page.theme_mode = THEME_MODES.get(mode, ft.ThemeMode.SYSTEM)
    page.bgcolor = ft.Colors.SURFACE


# ---------------------------------------------------------------- building blocks
def card(content, padding=16, on_click=None, bgcolor=CARD, radius=18) -> ft.Container:
    return ft.Container(content, bgcolor=bgcolor, border_radius=radius, padding=padding, on_click=on_click,
                        ink=on_click is not None)


def section(title, action=None, on_action=None) -> ft.Row:
    controls = [ft.Text(title, size=16, weight=ft.FontWeight.W_600, expand=True)]
    if action:
        controls.append(ft.TextButton(action, on_click=on_action))
    return ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def muted(text, size=12, **kwargs) -> ft.Text:
    return ft.Text(text, size=size, color=kwargs.pop("color", MUTED), **kwargs)


def stat(label, value, color=None, sub=None) -> ft.Container:
    controls = [muted(label), ft.Text(value, size=18, weight=ft.FontWeight.W_700, color=color)]
    if sub:
        controls.append(muted(sub, size=11))
    return card(ft.Column(controls, spacing=4), padding=14)


def dot(color, size=10) -> ft.Container:
    return ft.Container(width=size, height=size, border_radius=3, bgcolor=color)


def icon_badge(icon, color, size=40) -> ft.Container:
    return ft.Container(ft.Icon(icon, color=ft.Colors.WHITE, size=size * 0.5), width=size, height=size,
                        border_radius=size * 0.32, bgcolor=color, alignment=ft.Alignment.CENTER)


def grouped(rows: list, empty=None) -> list:
    """Rows (ListTiles...) inside one card separated by hairlines; `empty` shown when there are none."""
    if not rows:
        return [empty] if empty is not None else []
    items = []
    for i, row in enumerate(rows):
        if i:
            items.append(ft.Divider(height=1, leading_indent=16, trailing_indent=16))
        items.append(row)
    return [card(ft.Column(items, spacing=0), padding=ft.Padding.symmetric(vertical=4))]


def text_badge(text, color, size=40) -> ft.Container:
    return ft.Container(ft.Text(text, size=size * 0.32, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE),
                        width=size, height=size, border_radius=size * 0.32, bgcolor=color,
                        alignment=ft.Alignment.CENTER)


ASSET_BADGES = {"currency": ("#0EA5E9", None), "gold": ("#D97706", "Au"), "silver": ("#64748B", "Ag")}
CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€"}


def asset_badge(asset: dict, size=40) -> ft.Container:
    color, text = ASSET_BADGES.get(asset.get("asset_type"), ("#64748B", None))
    return text_badge(text or CURRENCY_SYMBOLS.get(asset["code"], asset["code"][:2]), color, size)


def kind_badge(kind: str, card_spend=False, dimmed=False, size=40) -> ft.Container:
    """Round badge for a money movement: income arrow, expense arrow or card."""
    is_expense = kind == "expense"
    icon = ft.Icons.CREDIT_CARD if card_spend else (ft.Icons.SOUTH_WEST if not is_expense else ft.Icons.NORTH_EAST)
    color = MUTED if dimmed else (EXPENSE if is_expense else INCOME)
    bg = ft.Colors.SURFACE_CONTAINER_HIGH if dimmed else (
        ft.Colors.ERROR_CONTAINER if is_expense else ft.Colors.TERTIARY_CONTAINER)
    return ft.Container(ft.Icon(icon, size=size * 0.5, color=color), width=size, height=size,
                        border_radius=size / 2, bgcolor=bg, alignment=ft.Alignment.CENTER)


CATEGORY_ICONS = {
    "market": ft.Icons.SHOPPING_CART, "yeme-içme": ft.Icons.RESTAURANT, "faturalar": ft.Icons.BOLT,
    "kira": ft.Icons.HOME, "ulaşım": ft.Icons.DIRECTIONS_CAR, "sağlık": ft.Icons.FAVORITE,
    "eğitim": ft.Icons.SCHOOL, "giyim": ft.Icons.CHECKROOM, "eğlence": ft.Icons.MOVIE,
    "abonelikler": ft.Icons.SUBSCRIPTIONS, "online alışveriş": ft.Icons.SHOPPING_BAG,
    "ev & elektronik": ft.Icons.DEVICES, "kişisel bakım": ft.Icons.SPA, "para transferi": ft.Icons.SWAP_HORIZ,
    "nakit çekim": ft.Icons.LOCAL_ATM, "banka masrafı": ft.Icons.ACCOUNT_BALANCE, "kredi/borç": ft.Icons.REQUEST_QUOTE,
    "yatırım": ft.Icons.TRENDING_UP, "maaş": ft.Icons.WORK, "ek gelir": ft.Icons.PAYMENTS,
    "gelen transfer": ft.Icons.CALL_RECEIVED, "iade": ft.Icons.REPLAY, "faiz/getiri": ft.Icons.PERCENT,
}


def tr_lower(text: str) -> str:
    """Turkish-aware lowercase ('İ'.lower() would give 'i' + combining dot)."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def category_icon(c: dict):
    """Icon for a category: stored icon name, else a match on the default category names."""
    stored = (c.get("icon") or "").upper()
    if stored and hasattr(ft.Icons, stored):
        return getattr(ft.Icons, stored)
    return CATEGORY_ICONS.get(tr_lower(c["name"]), ft.Icons.LABEL)


def category_color(c: dict) -> str:
    """Stored color, else a stable palette pick from the name (Python's hash() is randomized per run)."""
    return c.get("color") or CHART[sum(map(ord, c["name"])) % (len(CHART) - 1)]


def amount_color(value):
    number = Decimal(str(value or 0))
    return INCOME if number > 0 else EXPENSE if number < 0 else None


# ---------------------------------------------------------------- charts
def donut(segments: list[tuple[float, str]], size=124, thickness=16, center_top="", center_bottom="") -> ft.Stack:
    """Ring chart; segments = [(value, color)]."""
    total = sum(v for v, _ in segments) or 1
    radius = (size - thickness) / 2
    shapes = [cv.Circle(size / 2, size / 2, radius, ft.Paint(color=TRACK, stroke_width=thickness,
                                                             style=ft.PaintingStyle.STROKE))]
    start = -math.pi / 2
    for value, color in segments:
        sweep = 2 * math.pi * value / total
        if sweep <= 0:
            continue
        shapes.append(cv.Arc(thickness / 2, thickness / 2, size - thickness, size - thickness, start,
                             max(sweep - 0.03, 0.01),
                             paint=ft.Paint(color=color, stroke_width=thickness, style=ft.PaintingStyle.STROKE)))
        start += sweep
    center = ft.Column([muted(center_top, size=11), ft.Text(center_bottom, size=14, weight=ft.FontWeight.W_700)],
                       spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER)
    return ft.Stack([cv.Canvas(shapes, width=size, height=size),
                     ft.Container(center, width=size, height=size, alignment=ft.Alignment.CENTER)],
                    width=size, height=size)


def grouped_bars(groups: list[tuple[str, list[float]]], colors: list[str], height=110, bar_width=12) -> ft.Row:
    """Vertical bars per group (e.g. month -> [income, expense]), scaled to the largest value."""
    top = max((v for _, values in groups for v in values), default=0) or 1

    def bar(value, color):
        return ft.Container(width=bar_width, height=max(height * value / top, 3 if value else 0), bgcolor=color,
                            border_radius=ft.BorderRadius.only(top_left=4, top_right=4, bottom_left=2, bottom_right=2))

    columns = [
        ft.Column([
            ft.Container(ft.Row([bar(v, c) for v, c in zip(values, colors)], spacing=3,
                                vertical_alignment=ft.CrossAxisAlignment.END),
                         height=height, alignment=ft.Alignment.BOTTOM_CENTER),
            muted(label, size=10),
        ], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        for label, values in groups
    ]
    return ft.Row(columns, spacing=4)


class LineChart(ft.Container):
    """Area + line chart that redraws on resize. values: oldest first."""

    def __init__(self, values: list[float], height=90, color=ACCENT, fill="#2014B8A6"):
        self.values, self.color, self.fill = values, color, fill
        self.canvas = cv.Canvas([], height=height, expand=True, on_resize=self._resize, resize_interval=100)
        super().__init__(self.canvas, height=height)

    def _resize(self, e: cv.CanvasResizeEvent):
        self._draw(e.width, e.height)
        self.canvas.update()

    def _draw(self, width, height):
        values = self.values
        if len(values) < 2 or width <= 0:
            self.canvas.shapes = []
            return
        low, high = min(values), max(values)
        span = (high - low) or 1
        pad = 6
        points = [(i * width / (len(values) - 1), pad + (height - 2 * pad) * (1 - (v - low) / span))
                  for i, v in enumerate(values)]
        line = [cv.Path.MoveTo(*points[0])] + [cv.Path.LineTo(x, y) for x, y in points[1:]]
        area = line + [cv.Path.LineTo(width, height), cv.Path.LineTo(0, height), cv.Path.Close()]
        self.canvas.shapes = [
            cv.Path(area, paint=ft.Paint(color=self.fill, style=ft.PaintingStyle.FILL)),
            cv.Path(line, paint=ft.Paint(color=self.color, stroke_width=3, style=ft.PaintingStyle.STROKE,
                                         stroke_cap=ft.StrokeCap.ROUND, stroke_join=ft.StrokeJoin.ROUND)),
            cv.Circle(*points[-1], 4, ft.Paint(color=self.color, style=ft.PaintingStyle.FILL)),
        ]
