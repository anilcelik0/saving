"""Reports: category breakdown (+ drill-down), monthly trend, net worth and portfolio value history."""

from datetime import date
from decimal import Decimal

import flet as ft

from .choices import KINDS, MONTHS
from .theme import (
    CARD, CHART, EXPENSE, EXPENSE_BAR, INCOME, INCOME_BAR, MUTED, LineChart, card, donut, dot, grouped,
    grouped_bars, icon_badge,
)
from .transactions import transaction_tile
from .ui import dropdown, empty_text, fmt_date, fmt_money, fmt_number, fmt_pct, guarded

GREEN, RED, GREY = INCOME, EXPENSE, MUTED
PERIODS = [("1", "Tek ay"), ("3", "Son 3 ay"), ("6", "Son 6 ay"), ("12", "Son 12 ay")]
HISTORY_LENGTHS = [("6", "Son 6 ay"), ("12", "Son 12 ay"), ("24", "Son 24 ay")]


def month_name(key: str) -> str:
    y, m = key.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def _color(value, good_when_positive=True):
    if value in (None, ""):
        return None
    number = Decimal(str(value))
    if number == 0:
        return None
    return GREEN if (number > 0) == good_when_positive else RED


def _row(text, value, bold=False, color=None):
    weight = ft.FontWeight.BOLD if bold else None
    return ft.Row([ft.Text(text, weight=weight, expand=True), ft.Text(value, weight=weight, color=color)])


def _detail(text, color=None):
    return ft.Text(text, size=12, color=color or GREY)


class ReportsScreen:
    def __init__(self, state):
        push = state.router.push
        self.view = ft.View(
            route="/reports",
            appbar=ft.AppBar(title=ft.Text("Raporlar")),
            controls=[ft.ListView(grouped([
                ft.ListTile(leading=icon_badge(ft.Icons.PIE_CHART, "#0F766E", size=36), title=ft.Text("Kategori dağılımı"),
                            subtitle=ft.Text("Gider/gelir kategorilere göre, önceki döneme göre fark"),
                            on_click=lambda e: push(CategoryReport(state).view)),
                ft.ListTile(leading=icon_badge(ft.Icons.BAR_CHART, "#D97706", size=36), title=ft.Text("Aylık trend"),
                            subtitle=ft.Text("Ay ay gelir, gider, birikim ve birikim oranı"),
                            on_click=lambda e: push(TrendReport(state).view)),
                ft.ListTile(leading=icon_badge(ft.Icons.ACCOUNT_BALANCE_WALLET, "#1D4ED8", size=36), title=ft.Text("Net varlık"),
                            subtitle=ft.Text("Hesaplar + yatırımlar, ay sonları"),
                            on_click=lambda e: push(WealthReport(state, "net").view)),
                ft.ListTile(leading=icon_badge(ft.Icons.SAVINGS, "#7C3AED", size=36), title=ft.Text("Portföy değer geçmişi"),
                            subtitle=ft.Text("Altın/döviz + mevduat değeri ve maliyete göre fark"),
                            on_click=lambda e: push(WealthReport(state, "portfolio").view)),
            ]), expand=True, padding=16)],
            padding=0,
        )


class _Report:
    """Scaffold: month navigation (period end, never beyond the current month) + options row + body."""

    route = "/report"
    title = ""

    def __init__(self, state, options: list[ft.Control]):
        self.state = state
        self.page = state.page
        today = date.today()
        self.year, self.month = today.year, today.month
        self.max_index = today.year * 12 + today.month - 1
        self.month_label = ft.Text(weight=ft.FontWeight.W_600)
        self.next_button = ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=lambda e: self._shift(1))
        self.body = ft.Column(spacing=12)
        self.view = ft.View(
            route=self.route,
            appbar=ft.AppBar(title=ft.Text(self.title)),
            controls=[ft.ListView([
                ft.Row([ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=lambda e: self._shift(-1), tooltip="Önceki ay"),
                        ft.Container(self.month_label, bgcolor=CARD, border_radius=999,
                                     padding=ft.Padding.symmetric(horizontal=16, vertical=8)),
                        self.next_button], alignment=ft.MainAxisAlignment.CENTER),
                ft.Row(options, wrap=True),
                self.body,
            ], expand=True, padding=16, spacing=12)],
            padding=0,
        )
        for control in options:
            control.on_select = lambda e: self.page.run_task(self.refresh)
        self.page.run_task(self.refresh)

    @property
    def month_key(self):
        return f"{self.year:04d}-{self.month:02d}"

    def _shift(self, delta):
        index = min(self.year * 12 + self.month - 1 + delta, self.max_index)
        self.year, self.month = index // 12, index % 12 + 1
        self.page.run_task(self.refresh)

    async def refresh(self):
        self.month_label.value = f"Bitiş: {MONTHS[self.month - 1]} {self.year}"
        self.next_button.disabled = self.year * 12 + self.month - 1 >= self.max_index
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        raise NotImplementedError


# ---------------------------------------------------------------- categories
class CategoryReport(_Report):
    route, title = "/report-categories", "Kategori dağılımı"

    def __init__(self, state):
        self.kind = dropdown("Tür", KINDS, "expense")
        self.period = dropdown("Dönem", PERIODS, "1")
        self.kind.width = self.period.width = 160
        super().__init__(state, [self.kind, self.period])

    async def _fetch(self):
        months = int(self.period.value)
        r = await self.state.reports.categories(self.kind.value, self.month_key, months)
        p, prev = r["period"], r["previous_period"]
        span = month_name(p["end_month"]) if months == 1 else f"{month_name(p['start_month'])} – {month_name(p['end_month'])}"
        head = [
            _row("Toplam", fmt_money(r["total"]), bold=True),
            _detail(f"{span} · önceki dönem ({month_name(prev['start_month'])}"
                    f"{'' if months == 1 else ' – ' + month_name(prev['end_month'])}) {fmt_money(r['previous_total'])}"
                    f" · fark {fmt_pct(r['change_pct'])}",
                    _color(r["change_pct"], good_when_positive=self.kind.value == "income")),
        ]
        active = [i for i in r["items"] if Decimal(i["amount"]) > 0]
        if active:
            head.append(ft.Row([donut([(float(i["amount"]), CHART[n % len(CHART)]) for n, i in enumerate(active)],
                                      size=140, thickness=18, center_top="toplam",
                                      center_bottom=fmt_money(r["total"]).replace(",00 ₺", " ₺"))],
                               alignment=ft.MainAxisAlignment.CENTER))
        self.colors = {i["category"]: CHART[n % len(CHART)] for n, i in enumerate(active)}
        rows = [card(ft.Column(head, spacing=10))]
        tiles = [self._tile(i, months) for i in r["items"]]
        rows.append(card(ft.Column(tiles, spacing=6)) if tiles else empty_text("Bu dönemde kayıt yok."))
        self.body.controls = rows
        self.page.update()

    def _tile(self, item, months):
        share = Decimal(item["pct"] or 0)
        change = f"önceki {fmt_money(item['previous'])} · {fmt_pct(item['change_pct'])}" if item["previous"] != "0.00" \
            else "önceki dönemde yok"
        return ft.Container(
            ft.Column([
                ft.Row([dot(self.colors.get(item["category"], MUTED)),
                        ft.Text(item["name"], expand=True, weight=ft.FontWeight.W_500),
                        ft.Text(f"{fmt_money(item['amount'])} · %{fmt_number(share, 1)}")]),
                ft.ProgressBar(value=float(share) / 100, bar_height=6, border_radius=3,
                               color=self.colors.get(item["category"], MUTED), bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH),
                _detail(f"{item['count']} kayıt · {change}",
                        _color(item["change_pct"], good_when_positive=self.kind.value == "income")),
            ], spacing=2),
            padding=ft.Padding.symmetric(vertical=4),
            on_click=(lambda e: self.state.router.push(
                CategoryTransactions(self.state, item, self.kind.value, self.month_key, months).view))
            if item["count"] else None,
        )


class CategoryTransactions:
    """Transactions behind one category row (same period scope as the report)."""

    def __init__(self, state, item, kind, month, months):
        self.state = state
        self.page = state.page
        self.args = (item["category"], kind, month, months)
        self.list = ft.ListView(expand=True, padding=16)
        self.view = ft.View(route="/report-category", appbar=ft.AppBar(title=ft.Text(item["name"])),
                            controls=[self.list], padding=0)
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        rows = await self.state.reports.category_transactions(*self.args)
        self.list.controls = grouped([transaction_tile(self.state, t, self.refresh) for t in rows], empty_text("Kayıt yok."))
        self.page.update()


# ---------------------------------------------------------------- trend
class TrendReport(_Report):
    route, title = "/report-trend", "Aylık trend"

    def __init__(self, state):
        self.length = dropdown("Dönem", HISTORY_LENGTHS, "12")
        self.length.width = 160
        super().__init__(state, [self.length])

    async def _fetch(self):
        r = await self.state.reports.trend(self.month_key, int(self.length.value))
        a = r["averages"]
        averages = [
            ft.Text(f"Aylık ortalama ({a['months']} ay, kaydı olan aylar)", weight=ft.FontWeight.W_600),
            _row("Gelir", fmt_money(a["income"])),
            _row("Gider", fmt_money(a["expense"])),
            _row("Birikim", fmt_money(a["saving"]), color=_color(a["saving"])),
            _row("Birikim oranı", fmt_pct(a["saving_rate"]), color=_color(a["saving_rate"])),
            _row("Yatırıma giden", fmt_money(a["investment_out"])),
            _detail("Birikim = gelir − gider; yatırım alışları/mevduat gider sayılmaz, "
                    "yatırımdan gelen TL ve mevduat kapanışları gelir sayılmaz."),
        ]
        chart = [m for m in r["months"]][-12:]
        rows = [
            card(ft.Column([
                grouped_bars([(MONTHS[int(m["month"][5:7]) - 1][:3], [float(m["income"]), float(m["expense"])])
                              for m in chart], [INCOME_BAR, EXPENSE_BAR], bar_width=8 if len(chart) > 6 else 12),
                ft.Row([ft.Row([dot(INCOME_BAR), _detail("Gelir")], spacing=6),
                        ft.Row([dot(EXPENSE_BAR), _detail("Gider")], spacing=6)], spacing=14),
            ], spacing=10)),
            card(ft.Column(averages, spacing=6)),
        ]
        top = max((max(Decimal(m["income"]), Decimal(m["expense"])) for m in r["months"]), default=Decimal(0))
        rows.append(card(ft.Column([self._month(m, top) for m in reversed(r["months"])], spacing=4)))
        self.body.controls = rows
        self.page.update()

    @staticmethod
    def _month(m, top):
        def bar(value, color):
            return ft.ProgressBar(value=float(Decimal(value) / top) if top else 0, color=color, bar_height=6,
                                  border_radius=3, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH)

        extra = []
        if m["investment_out"] != "0.00":
            extra.append(f"yatırıma {fmt_money(m['investment_out'])}")
        if m["investment_in"] != "0.00":
            extra.append(f"yatırımdan {fmt_money(m['investment_in'])}")
        return ft.Container(ft.Column([
            _row(month_name(m["month"]), f"Birikim {fmt_money(m['saving'])} ({fmt_pct(m['saving_rate'])})", bold=True,
                 color=_color(m["saving"])),
            _detail(f"Gelir {fmt_money(m['income'])}"), bar(m["income"], INCOME_BAR),
            _detail(f"Gider {fmt_money(m['expense'])}" + (f" · {' · '.join(extra)}" if extra else "")), bar(m["expense"], EXPENSE_BAR),
        ], spacing=2), padding=ft.Padding.symmetric(vertical=6))


# ---------------------------------------------------------------- net worth / portfolio history
class WealthReport(_Report):
    """mode 'net': cash + investments; mode 'portfolio': holdings and deposits vs. cost."""

    def __init__(self, state, mode):
        self.mode = mode
        self.route = f"/report-{mode}"
        self.title = "Net varlık" if mode == "net" else "Portföy değer geçmişi"
        self.length = dropdown("Dönem", HISTORY_LENGTHS, "12")
        self.length.width = 160
        super().__init__(state, [self.length])

    async def _fetch(self):
        r = await self.state.reports.wealth(self.month_key, int(self.length.value))
        points = r["points"]
        if not points:
            self.body.controls = [empty_text("Veri yok.")]
            self.page.update()
            return
        first, last = points[0], points[-1]
        if self.mode == "net":
            rows = [
                _row("Net varlık", fmt_money(last["net_worth"]), bold=True),
                _detail(f"{fmt_date(last['date'])} itibarıyla · dönem başından fark {fmt_money(r['net_worth_change'])} "
                        f"({fmt_pct(r['net_worth_change_pct'])})", _color(r["net_worth_change"])),
                _detail("Net varlık = hesap bakiyeleri + yatırımlar (altın/döviz güncel alış fiyatıyla, mevduat "
                        "işleyen faiziyle)."),
            ]
        else:
            change = Decimal(last["investments"]) - Decimal(first["investments"])
            rows = [
                _row("Yatırımlar", fmt_money(last["investments"]), bold=True),
                _detail(f"Maliyete göre fark {fmt_money(last['investments_gain'])} · dönem başından değişim "
                        f"{fmt_money(change)}", _color(last["investments_gain"])),
            ]
        key = "net_worth" if self.mode == "net" else "investments"
        if len(points) > 1:
            rows += [LineChart([float(p[key]) for p in points], height=120),
                     ft.Row([_detail(month_name(first["month"])), ft.Container(expand=True),
                             _detail(month_name(last["month"]))])]
        if not all(p["priced"] for p in points):
            rows.append(_detail("* O tarihte kayıtlı fiyat olmayan aylarda varlıklar maliyetle sayıldı "
                                "(fiyatlar uygulamada günlük kaydedilmeye başladığı tarihten itibaren var)."))
        rows = [card(ft.Column(rows, spacing=8)),
                card(ft.Column([self._point(p) for p in reversed(points)], spacing=4))]
        self.body.controls = rows
        self.page.update()

    def _point(self, p):
        mark = "" if p["priced"] else " *"
        if self.mode == "net":
            lines = [_row(f"{month_name(p['month'])}{mark}", fmt_money(p["net_worth"]), bold=True),
                     _detail(f"Hesaplar {fmt_money(p['cash'])} · Yatırımlar {fmt_money(p['investments'])}")]
        else:
            lines = [_row(f"{month_name(p['month'])}{mark}", fmt_money(p["investments"]), bold=True),
                     _detail(f"Altın/döviz {fmt_money(p['assets_value'])} (maliyet {fmt_money(p['assets_cost'])}) · "
                             f"Mevduat {fmt_money(p['deposits_value'])} (anapara {fmt_money(p['deposits_principal'])})"),
                     _detail(f"Fark {fmt_money(p['investments_gain'])}", _color(p["investments_gain"]))]
        return ft.Container(ft.Column(lines, spacing=2), padding=ft.Padding.symmetric(vertical=4))
