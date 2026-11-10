import flet as ft

from .choices import FREQUENCIES, label
from .transactions import open_entry_form
from .theme import EXPENSE, INCOME, MUTED, card, grouped, icon_badge, muted
from .ui import fmt_date, fmt_money, guarded, toast


class AutoPaymentsScreen:
    """
    More > Otomatik ödemelerim: recurring and installment payments.
    Editing opens the next pending occurrence (choose "this and following" to change the whole plan);
    deleting with "this and following" stops the plan, paid history stays.
    """

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.Column(spacing=0)
        self.view = ft.View(
            route="/auto-payments",
            appbar=ft.AppBar(title=ft.Text("Otomatik ödemelerim")),
            floating_action_button=ft.FloatingActionButton(
                icon=ft.Icons.ADD, on_click=lambda e: open_entry_form(state, None, self.refresh, repeat="recurring")
            ),
            controls=[ft.ListView([
                muted("Günü gelen otomatik ödemeler hesaba kendiliğinden işlenir. Düzenlerken "
                      "'Bu ve sonraki bekleyenler'i seçerseniz plan tümüyle güncellenir."),
                self.list,
            ], expand=True, padding=16, spacing=12)],
            padding=0,
        )
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        plans = await self.state.budget.series()
        self.list.controls = grouped([self._tile(p) for p in plans],
                                     card(muted("Düzenli veya taksitli ödeme yok. + ile ekleyebilirsiniz.")))
        self.page.update()

    def _tile(self, p):
        nxt = p["next_occurrence"]
        if p["series_type"] == "installment":
            plan = f"Taksit {p['paid_count'] + 1}/{p['installment_count']}"
        else:
            plan = label(FREQUENCIES, p["frequency"])
        where = self.state.card_name(p["account"]) if p["is_card"] else self.state.account_name(p["account"])
        parts = [plan, "Otomatik" if p["auto_pay"] else "Manuel", where]
        if nxt:
            parts.insert(0, f"Sıradaki: {fmt_date(nxt['date'])}")
        sign = "+" if p["kind"] == "income" else "−"
        return ft.ListTile(
            leading=icon_badge(ft.Icons.AUTORENEW if p["auto_pay"] else ft.Icons.EVENT_REPEAT,
                               "#0EA5E9" if p["auto_pay"] else "#64748B", size=36),
            title=ft.Text(p["description"], weight=ft.FontWeight.W_500),
            subtitle=ft.Text(" · ".join(parts), color=MUTED),
            trailing=ft.Text(sign + fmt_money(nxt["amount"] if nxt else p["amount"]), weight=ft.FontWeight.W_600,
                             color=INCOME if p["kind"] == "income" else EXPENSE),
            on_click=lambda e: self._open(p),
        )

    def _open(self, plan):
        if not plan["next_occurrence"]:
            toast(self.page, "Bu planın bekleyen ödemesi kalmadı.", error=True)
            return
        open_entry_form(self.state, plan["next_occurrence"], self.refresh)
