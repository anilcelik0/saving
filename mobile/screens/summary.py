import asyncio
from datetime import date
from decimal import Decimal

import flet as ft

from .choices import MONTHS
from .theme import (
    CARD, CHART, EXPENSE, EXPENSE_BAR, INCOME, INCOME_BAR, LineChart, amount_color, card, donut, dot,
    grouped_bars, muted, section, stat,
)
from .ui import fmt_money, fmt_number, fmt_pct, guarded

TOP_CATEGORIES = 5


def month_short(key: str) -> str:
    return MONTHS[int(key[5:7]) - 1][:3]


def short_money(value) -> str:
    """Compact amount for chart centers: 116000 -> '116 B₺', 1250000 -> '1,25 M₺'."""
    number = abs(Decimal(str(value or 0)))
    if number >= 1_000_000:
        return fmt_number(number / 1_000_000, 2) + " M₺"
    if number >= 10_000:
        return fmt_number(number / 1000, 0) + " B₺"
    return fmt_money(number)


class SummaryTab:
    """Home: balance, month income/expense, spending ring, 6-month bars, net worth line, upcoming payments."""

    title = "Özet"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        today = date.today()
        self.year, self.month = today.year, today.month
        self.fab = None
        self.month_label = ft.Text(weight=ft.FontWeight.W_600)
        self.body = ft.Column(spacing=14)
        self.control = ft.ListView(
            [
                ft.Row([
                    ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=lambda e: self._shift(-1), tooltip="Önceki ay"),
                    ft.Container(self.month_label, bgcolor=CARD, border_radius=999,
                                 padding=ft.Padding.symmetric(horizontal=16, vertical=8)),
                    ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=lambda e: self._shift(1), tooltip="Sonraki ay"),
                ], alignment=ft.MainAxisAlignment.CENTER),
                self.body,
            ],
            expand=True,
            padding=ft.Padding.only(left=16, right=16, bottom=96),
        )

    @property
    def upcoming_days(self) -> int:
        return self.state.settings.upcoming_days if self.state.settings else 30

    @property
    def month_key(self):
        return f"{self.year:04d}-{self.month:02d}"

    def _shift(self, delta):
        index = self.year * 12 + self.month - 1 + delta
        self.year, self.month = index // 12, index % 12 + 1
        self.page.run_task(self.refresh)

    @property
    def hidden(self) -> bool:
        return bool(self.state.settings and self.state.settings.hide_amounts)

    def money(self, value, short=False) -> str:
        if self.hidden:
            return "•••• ₺"
        return short_money(value) if short else fmt_money(value)

    async def _toggle_hidden(self, e):
        await self.state.settings.set("hide_amounts", "false" if self.hidden else "true")
        await self.refresh()

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        self.month_label.value = f"{MONTHS[self.month - 1]} {self.year}"
        report_month = min(self.month_key, date.today().strftime("%Y-%m"))  # reports never look ahead
        budget, reports = self.state.budget, self.state.reports
        s, cats, trend, wealth, upcoming = await asyncio.gather(
            budget.summary(self.month_key),
            reports.categories("expense", self.month_key, 1),
            reports.trend(report_month, 6),
            reports.wealth(report_month, 6),
            budget.activity_upcoming(self.upcoming_days),
        )
        self.body.controls = [
            self._hero(s),
            ft.Row([
                ft.Container(stat("Gelir", "+" + self.money(s["income"]), INCOME,
                                  f"bekleyen {self.money(s['income_pending'])}"), expand=True),
                ft.Container(stat("Gider", "−" + self.money(s["expense"]), EXPENSE,
                                  f"bekleyen {self.money(s['expense_pending'])}"), expand=True),
            ], spacing=12),
            self._spending(cats),
            self._trend(trend),
            self._wealth(wealth),
            self._upcoming(upcoming),
            self._accounts(s),
        ]
        self.page.update()

    # ---------------------------------------------------------------- parts
    def _hero(self, s):
        on = ft.Colors.ON_PRIMARY
        lines = [
            ft.Row([ft.Text("Toplam bakiye", size=13, color=on, opacity=0.85, expand=True),
                    ft.IconButton(ft.Icons.VISIBILITY_OFF_OUTLINED if self.hidden else ft.Icons.VISIBILITY_OUTLINED,
                                  icon_color=on, icon_size=20, tooltip="Tutarları göster" if self.hidden
                                  else "Tutarları gizle", on_click=self._toggle_hidden)]),
            ft.Text(self.money(s["current_balance"]), size=32, weight=ft.FontWeight.W_700, color=on),
        ]
        if s["projected_balance"] is not None:
            lines.append(ft.Text(f"Ay sonu tahmini {self.money(s['projected_balance'])}", size=13, color=on, opacity=0.85))
        overdue = Decimal(s["overdue_expense"]) + Decimal(s["overdue_income"])
        if overdue:
            lines.append(ft.Container(
                ft.Text(f"Geciken: gider {self.money(s['overdue_expense'])} · gelir {self.money(s['overdue_income'])}",
                        size=12, color=on),
                bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.BLACK), border_radius=10,
                padding=ft.Padding.symmetric(horizontal=10, vertical=6)))
        hero = card(ft.Column(lines, spacing=6), padding=20, bgcolor=ft.Colors.PRIMARY, radius=22)
        hero.expand = True
        return ft.Row([hero])  # full width

    def _open_report(self, factory):
        from . import reports
        self.state.router.push(factory(reports).view)

    def _spending(self, r):
        items = [i for i in r["items"] if Decimal(i["amount"]) > 0]
        header = section(f"Harcama dağılımı · {MONTHS[self.month - 1]}", "Rapor",
                         lambda e: self._open_report(lambda m: m.CategoryReport(self.state)))
        if not items:
            return card(ft.Column([header, muted("Bu ay harcama yok.")], spacing=8))
        top, rest = items[:TOP_CATEGORIES], items[TOP_CATEGORIES:]
        rows = [(i["name"], Decimal(i["amount"]), Decimal(i["pct"] or 0)) for i in top]
        if rest:
            rows.append(("Diğer", sum((Decimal(i["amount"]) for i in rest), Decimal(0)),
                         sum((Decimal(i["pct"] or 0) for i in rest), Decimal(0))))
        colors = CHART[:len(rows) - 1] + [CHART[-1] if rest else CHART[len(rows) - 1]]
        legend = ft.Column([
            ft.Row([dot(color), ft.Text(name, size=13, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"%{fmt_number(share, 0)}", size=13, weight=ft.FontWeight.W_600)], spacing=8)
            for (name, _, share), color in zip(rows, colors)
        ], spacing=8, expand=True)
        ring = donut([(float(amount), color) for (_, amount, _), color in zip(rows, colors)],
                     center_top="toplam", center_bottom=self.money(r["total"], short=True))
        return card(ft.Column([header, ft.Row([ring, legend], spacing=16,
                                              vertical_alignment=ft.CrossAxisAlignment.CENTER)], spacing=10))

    def _trend(self, t):
        groups = [(month_short(m["month"]), [float(m["income"]), float(m["expense"])]) for m in t["months"]]
        header = section("Gelir · gider (son 6 ay)", "Rapor", lambda e: self._open_report(lambda m: m.TrendReport(self.state)))
        legend = ft.Row([
            ft.Row([dot(INCOME_BAR), muted("Gelir")], spacing=6),
            ft.Row([dot(EXPENSE_BAR), muted("Gider")], spacing=6),
            ft.Container(expand=True),
            muted(f"Ort. birikim oranı {fmt_pct(t['averages']['saving_rate'])}"),
        ], spacing=14)
        return card(ft.Column([header, grouped_bars(groups, [INCOME_BAR, EXPENSE_BAR]), legend], spacing=10))

    def _wealth(self, w):
        header = section("Net varlık", "Rapor", lambda e: self._open_report(lambda m: m.WealthReport(self.state, "net")))
        points = w["points"]
        if not points:
            return card(ft.Column([header, muted("Veri yok.")], spacing=8))
        last = points[-1]
        change = Decimal(w["net_worth_change"])
        controls = [
            header,
            ft.Row([ft.Text(self.money(last["net_worth"]), size=24, weight=ft.FontWeight.W_700),
                    ft.Text(("▲ " if change >= 0 else "▼ ") + self.money(abs(change)), size=13,
                            weight=ft.FontWeight.W_600, color=amount_color(change))],
                   vertical_alignment=ft.CrossAxisAlignment.END, spacing=10),
        ]
        if len(points) > 1:
            controls += [LineChart([float(p["net_worth"]) for p in points]),
                         ft.Row([muted(month_short(points[0]["month"]), size=11), ft.Container(expand=True),
                                 muted(month_short(last["month"]), size=11)])]
        controls.append(muted(f"Hesaplar {self.money(last['cash'])} · Yatırımlar {self.money(last['investments'])}"))
        return card(ft.Column(controls, spacing=8))

    def _upcoming(self, items):
        rows = []
        for item in items[:5]:
            if item["type"] == "transaction":
                t = item["transaction"]
                day, title = t["date"], t["description"] or self.state.category_name(t["category"])
                sign = "−" if t["kind"] == "expense" else "+"
                amount, color = sign + self.money(t["amount"]), EXPENSE if t["kind"] == "expense" else INCOME
                sub = self.state.account_name(t["account"])
            else:
                day, title = item["end"], item["card_name"]
                amount, color, sub = "−" + self.money(item["pending_amount"]), EXPENSE, "Kart ekstresi"
            overdue = day < date.today().isoformat()
            rows.append(ft.Row([
                ft.Container(
                    ft.Column([ft.Text(day[8:10], size=15, weight=ft.FontWeight.W_700),
                               ft.Text(MONTHS[int(day[5:7]) - 1][:3].upper(), size=10, weight=ft.FontWeight.W_600)],
                              spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                              alignment=ft.MainAxisAlignment.CENTER),
                    width=44, height=44, border_radius=14, alignment=ft.Alignment.CENTER,
                    bgcolor=ft.Colors.ERROR_CONTAINER if overdue else ft.Colors.PRIMARY_CONTAINER),
                ft.Column([ft.Text(title, size=14, weight=ft.FontWeight.W_500, max_lines=1,
                                   overflow=ft.TextOverflow.ELLIPSIS),
                           muted(("Gecikti · " if overdue else "") + sub)], spacing=2, expand=True),
                ft.Text(amount, size=14, weight=ft.FontWeight.W_600, color=color),
            ], spacing=12))
        body = rows or [muted(f"Önümüzdeki {self.upcoming_days} günde bekleyen ödeme yok.")]
        return card(ft.Column([section(f"Yaklaşan ödemeler ({self.upcoming_days} gün)"), *body], spacing=12))

    def _accounts(self, s):
        rows = [ft.Row([ft.Text(a["name"], size=14, expand=True), ft.Text(self.money(a["balance"]), size=14,
                                                                          weight=ft.FontWeight.W_600)])
                for a in s["accounts"]]
        body = rows or [muted("Henüz hesap yok. + > Hesap ekle ile açılış bakiyesiyle ekleyin.")]
        if s["card_cycles"]:
            body.append(muted("Kart harcamaları bu ay ekstre dönemine göre sayılır: " + ", ".join(
                f"{c['name']} {c['start'][8:10]}.{c['start'][5:7]}–{c['end'][8:10]}.{c['end'][5:7]}" for c in s["card_cycles"])))
        return card(ft.Column([section("Hesaplar"), *body], spacing=10))
