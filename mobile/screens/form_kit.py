"""
Data-entry form style ("big amount + chips"): a large centered amount, one-tap chip groups, a category icon grid,
date chips, a collapsible "more" section and a sticky action button that repeats the amount.
"""

from datetime import date, datetime, timedelta

import flet as ft

from .theme import ACCENT, CARD, CATEGORY_ICONS, MUTED, category_color, category_icon, icon_badge, muted, tr_lower
from .ui import confirm, fmt_date, guarded, money_input_value

OUTLINE = ft.Colors.OUTLINE_VARIANT


def _safe_update(control: ft.Control):
    try:
        control.update()
    except RuntimeError:
        pass  # not mounted yet; the first page render shows the current state


# ---------------------------------------------------------------- inputs
def big_amount(value=None, hint="0,00", suffix="₺", on_change=None, text=None) -> ft.TextField:
    """Large centered number input (amount, quantity, principal). `text`: already formatted input value."""
    return ft.TextField(
        value=text if text is not None else money_input_value(value), hint_text=hint, keyboard_type=ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.CENTER, border=ft.NoInputBorder(), filled=False,
        text_style=ft.TextStyle(size=40, weight=ft.FontWeight.W_800),
        hint_style=ft.TextStyle(size=40, weight=ft.FontWeight.W_800, color=ft.Colors.OUTLINE),
        suffix=ft.Text(f" {suffix}", size=28, weight=ft.FontWeight.W_700) if suffix else None,
        content_padding=ft.Padding.symmetric(vertical=4), on_change=on_change,
    )


def inline_text(value="", hint="Açıklama ekle", width=240) -> ft.TextField:
    """Small centered underlined field placed under the big amount."""
    return ft.TextField(
        value=value or "", hint_text=hint, text_align=ft.TextAlign.CENTER, width=width, filled=False,
        border=ft.UnderlineInputBorder(side=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)), dense=True,
        text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_500),
    )


def hero(label, amount: ft.Control, *below: ft.Control) -> ft.Container:
    """label: text or a Text control (to change it later, e.g. "Toplam tutar")."""
    label = muted(label, size=13) if isinstance(label, str) else label
    return ft.Container(
        ft.Column([label, amount, *below], spacing=4,
                  horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=16, right=16, top=8, bottom=8),
    )


def field(label: str, control: ft.Control, visible=True) -> ft.Column:
    """Titled block: small bold label above the control."""
    return ft.Column([ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=MUTED), control],
                     spacing=10, visible=visible)


def plain_input(value="", hint="", number=False, multiline=False) -> ft.TextField:
    return ft.TextField(value=value or "", hint_text=hint, multiline=multiline,
                        keyboard_type=ft.KeyboardType.NUMBER if number else ft.KeyboardType.TEXT)


# ---------------------------------------------------------------- choices
class Chips:
    """Pill choices in a wrapping row. options: [(key, text)]. `allow_none`: tapping the selected one clears it."""

    def __init__(self, options, value=None, on_change=None, allow_none=False, selected_color=ACCENT,
                 selected_text=ft.Colors.ON_PRIMARY):
        self.options, self.value, self.on_change, self.allow_none = list(options), value, on_change, allow_none
        self.selected_color, self.selected_text = selected_color, selected_text
        self.control = ft.Row(wrap=True, spacing=8, run_spacing=8)
        self._render()

    def _chip(self, key, text):
        selected = key == self.value
        return ft.Container(
            ft.Text(text, size=13, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500,
                    color=self.selected_text if selected else None),
            padding=ft.Padding.symmetric(horizontal=14, vertical=12), border_radius=999,
            bgcolor=self.selected_color if selected else CARD,
            border=None if selected else ft.Border.all(1, OUTLINE),
            on_click=lambda e, k=key: self.select(k), ink=True,
        )

    def _render(self):
        self.control.controls = [self._chip(k, t) for k, t in self.options]

    def set_options(self, options, value=None):
        self.options = list(options)
        keys = [k for k, _ in self.options]
        self.value = value if value in keys else (None if self.allow_none or not keys else keys[0])
        self._render()

    def select(self, key):
        if key == self.value and self.allow_none:
            key = None
        self.value = key
        self._render()
        _safe_update(self.control)
        if self.on_change:
            self.on_change(key)


class Segmented:
    """Pill switch for 2-3 options (Gider / Gelir). colors: {key: (bg, fg)} for the selected state."""

    def __init__(self, options, value, on_change=None, colors=None, disabled=False):
        self.options, self.value, self.on_change = options, value, on_change
        self.colors, self.disabled = colors or {}, disabled
        self.control = ft.Container(bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, border_radius=999, padding=4)
        self._render()

    def _render(self):
        items = []
        for key, text in self.options:
            selected = key == self.value
            if self.disabled and not selected:
                continue
            bg, fg = self.colors.get(key, (CARD, None))
            items.append(ft.Container(
                ft.Text(text, size=14, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500,
                        color=fg if selected else MUTED),
                padding=ft.Padding.symmetric(horizontal=18, vertical=10), border_radius=999,
                bgcolor=bg if selected else None,
                on_click=None if self.disabled else (lambda e, k=key: self.select(k)),
            ))
        self.control.content = ft.Row(items, spacing=2, tight=True)

    def select(self, key):
        if key == self.value:
            return
        self.value = key
        self._render()
        _safe_update(self.control)
        if self.on_change:
            self.on_change(key)


class CategoryGrid:
    """4-column icon grid. Recently used first; the first 7 shown, the rest behind "Tümü". Tap again to clear."""

    COLUMNS = 4
    COLLAPSED = 7

    def __init__(self, categories: list[dict], value=None, recent: list[str] | None = None, on_change=None):
        self.value, self.on_change, self.recent = value, on_change, recent or []
        self.expanded = False
        self.control = ft.Column(spacing=8)
        self.set_categories(categories, value)

    def set_categories(self, categories, value=None):
        rank = {cid: i for i, cid in enumerate(self.recent)}
        common = {name: i for i, name in enumerate(CATEGORY_ICONS)}  # default categories, most common first
        self.categories = sorted(categories, key=lambda c: (rank.get(c["id"], len(rank)),
                                                            common.get(tr_lower(c["name"]), len(common)), c["name"]))
        self.value = value if any(c["id"] == value for c in categories) else None
        if self.value and all(c["id"] != self.value for c in self.categories[: self.COLLAPSED]):
            chosen = next(c for c in self.categories if c["id"] == self.value)
            self.categories.remove(chosen)
            self.categories.insert(0, chosen)
        self._render()

    def _tile(self, c):
        selected = c["id"] == self.value
        return ft.Container(
            ft.Column([icon_badge(category_icon(c), category_color(c), size=32),
                       ft.Text(c["name"], size=11, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500,
                               max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER)],
                      spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            height=76, padding=ft.Padding.symmetric(horizontal=4, vertical=10), border_radius=16,
            bgcolor=ft.Colors.PRIMARY_CONTAINER if selected else CARD,
            border=ft.Border.all(2, ACCENT) if selected else ft.Border.all(1, OUTLINE),
            on_click=lambda e, cid=c["id"]: self.select(cid), ink=True, expand=True,
        )

    def _toggle_tile(self):
        return ft.Container(
            ft.Column([ft.Icon(ft.Icons.EXPAND_LESS if self.expanded else ft.Icons.MORE_HORIZ, color=MUTED),
                       muted("Daha az" if self.expanded else "Tümü", size=11)],
                      spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                      alignment=ft.MainAxisAlignment.CENTER),
            height=76, border_radius=16, bgcolor=CARD, border=ft.Border.all(1, ft.Colors.OUTLINE),
            on_click=self._toggle, ink=True, expand=True,
        )

    def _render(self):
        overflow = len(self.categories) > self.COLLAPSED + 1
        shown = self.categories if (self.expanded or not overflow) else self.categories[: self.COLLAPSED]
        tiles = [self._tile(c) for c in shown]
        if overflow:
            tiles.append(self._toggle_tile())
        rows = []
        for i in range(0, len(tiles), self.COLUMNS):
            chunk = tiles[i:i + self.COLUMNS]
            chunk += [ft.Container(expand=True) for _ in range(self.COLUMNS - len(chunk))]
            rows.append(ft.Row(chunk, spacing=8))
        self.control.controls = rows or [muted("Bu tür için kategori yok.")]

    def _toggle(self, e):
        self.expanded = not self.expanded
        self._render()
        _safe_update(self.control)

    def select(self, cid):
        self.value = None if cid == self.value else cid
        self._render()
        _safe_update(self.control)
        if self.on_change:
            self.on_change(self.value)


class DateChips:
    """Bugün / Dün / Tarih seç. `.value` is a date (or None when optional and cleared), `.iso` 'YYYY-MM-DD'."""

    def __init__(self, page: ft.Page, value: date | str | None = None, optional=False, on_change=None,
                 shortcuts=True):
        self.page, self.optional, self.on_change, self.shortcuts = page, optional, on_change, shortcuts
        self.value = date.fromisoformat(value) if isinstance(value, str) else value
        if self.value is None and not optional:
            self.value = date.today()
        self.picker = ft.DatePicker(first_date=datetime(2000, 1, 1), last_date=datetime(2100, 12, 31),
                                    on_change=self._picked)
        self.chips = Chips([], on_change=self._chosen)
        self.control = self.chips.control
        self._render()

    def _render(self):
        today = date.today()
        options = []
        if self.shortcuts:
            options += [("today", "Bugün"), ("yesterday", "Dün")]
        shortcut = {today: "today", today - timedelta(days=1): "yesterday"}.get(self.value) if self.shortcuts else None
        custom = self.value is not None and shortcut is None
        options.append(("pick", fmt_date(self.value.isoformat()) if custom else "Tarih seç"))
        if self.optional and self.value is not None:
            options.append(("clear", "Temizle"))
        self.chips.set_options(options, shortcut or ("pick" if custom else None))

    def _chosen(self, key):
        today = date.today()
        if key == "pick":
            self.picker.value = datetime.combine(self.value or today, datetime.min.time())
            self.page.show_dialog(self.picker)
        elif key in ("today", "yesterday"):
            self.set(today if key == "today" else today - timedelta(days=1))
            return
        elif key == "clear":
            self.set(None)
            return
        self._render()  # "pick" opens the dialog; keep the current selection highlighted until a date comes back
        _safe_update(self.control)

    def _picked(self, e):
        picked = e.control.value
        if picked:
            self.set(picked.date() if isinstance(picked, datetime) else picked)

    def set(self, value):
        self.value = value
        self._render()
        _safe_update(self.control)
        if self.on_change:
            self.on_change(value)

    @property
    def iso(self) -> str | None:
        return self.value.isoformat() if self.value else None


class TermPicker:
    """Maturity date: quick term chips (32 / 46 / 92 / 181 days from `start()`) plus a date chip."""

    TERMS = (32, 46, 92, 181)

    def __init__(self, page: ft.Page, start, value: date | str | None, on_change=None):
        self.start, self.on_change = start, on_change
        self.terms = Chips([(n, f"{n} gün") for n in self.TERMS], allow_none=True, on_change=self._term)
        self.date = DateChips(page, value, shortcuts=False, on_change=self._dated)
        self.control = ft.Column([self.terms.control, self.date.control], spacing=8)
        self.sync()

    @property
    def value(self) -> date | None:
        return self.date.value

    @property
    def iso(self) -> str | None:
        return self.date.iso

    def sync(self):
        """Highlight the term chip matching the current dates (after the start date changes too)."""
        days = (self.value - self.start()).days if self.value and self.start() else None
        self.terms.value = days if days in self.TERMS else None
        self.terms._render()
        _safe_update(self.terms.control)

    def _term(self, days):
        if days:
            self.date.set(self.start() + timedelta(days=days))

    def _dated(self, value):
        self.sync()
        if self.on_change:
            self.on_change(value)


class Collapsible:
    """Bordered header row that expands to show extra fields. `summary()` gives the right-side text."""

    def __init__(self, title: str, controls: list[ft.Control], summary=None, expanded=False):
        self.title, self.summary, self.expanded = title, summary or (lambda: ""), expanded
        self.summary_text = muted("", size=13)
        self.chevron = ft.Icon(ft.Icons.EXPAND_MORE, color=MUTED, size=20)
        self.body = ft.Column(controls, spacing=16)
        header = ft.Container(
            ft.Row([ft.Text(title, size=14, weight=ft.FontWeight.W_500, expand=True), self.summary_text, self.chevron],
                   spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=16, vertical=14), on_click=self._toggle, ink=True,
            border_radius=16,
        )
        self.body_box = ft.Container(self.body, padding=ft.Padding.only(left=16, right=16, bottom=16))
        self.control = ft.Container(
            ft.Column([header, self.body_box], spacing=0),
            border=ft.Border.all(1, OUTLINE), border_radius=16, bgcolor=CARD,
        )
        self.refresh()

    def refresh(self):
        self.summary_text.value = self.summary()
        self.body_box.visible = self.expanded
        self.chevron.name = ft.Icons.EXPAND_LESS if self.expanded else ft.Icons.EXPAND_MORE

    def _toggle(self, e):
        self.expanded = not self.expanded
        self.refresh()
        _safe_update(self.control)


# ---------------------------------------------------------------- scaffold
class QuickForm:
    """
    Full-screen form: top bar (close · center widget · delete), scrollable body, sticky action button.
    `set_action(text)` updates the button label (e.g. "1.250 ₺ gider ekle").
    """

    def __init__(self, state, route, body: list[ft.Control], on_save, action_text="Kaydet", title=None,
                 center: ft.Control | None = None, on_delete=None, delete_message="Bu kayıt silinecek."):
        page = state.page
        self.page = page
        self.button = ft.FilledButton(action_text, height=54, expand=True,
                                      style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=18),
                                                           text_style=ft.TextStyle(size=16,
                                                                                   weight=ft.FontWeight.W_600)))

        async def save():
            self.button.disabled = True
            page.update()
            try:
                await on_save()
            finally:
                self.button.disabled = False
                page.update()

        self.button.on_click = guarded(page, save)

        if center is None and title:
            center = ft.Text(title, size=17, weight=ft.FontWeight.W_700)
        right = (ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Sil",
                               on_click=lambda e: confirm(page, delete_message, on_delete))
                 if on_delete else ft.Container(width=48))
        top = ft.Container(
            ft.Row([ft.IconButton(ft.Icons.CLOSE, tooltip="Kapat", on_click=lambda e: state.router.pop()),
                    ft.Container(center, expand=True, alignment=ft.Alignment.CENTER), right],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=4, right=4, top=8),
        )
        bottom = ft.Container(
            ft.Row([self.button]), bgcolor=ft.Colors.SURFACE,
            padding=ft.Padding.only(left=16, right=16, top=12, bottom=20),
            border=ft.Border.only(top=ft.BorderSide(1, OUTLINE)),
        )
        content = ft.ListView(body, spacing=20, expand=True, padding=ft.Padding.only(left=16, right=16, bottom=24))
        self.view = ft.View(route=route, controls=[ft.Column([top, content, bottom], spacing=0, expand=True)],
                            padding=0, bgcolor=ft.Colors.SURFACE)

    def set_action(self, text: str):
        self.button.content = text
        _safe_update(self.button)
