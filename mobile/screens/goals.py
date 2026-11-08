from datetime import date
from decimal import Decimal

import flet as ft

from .choices import GOAL_STATUSES, label
from .ui import (
    DateInput, FormError, confirm, dropdown, empty_text, fmt_date, fmt_money, form_view,
    guarded, money_field, parse_money, text_field,
)


class GoalsTab:
    title = "Birikim Hedefleri"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.list = ft.ListView(expand=True, padding=8)
        self.control = self.list
        self.fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda e: self._open_form(None))

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        goals = (await self.state.budget.goals.list(page_size=100))["results"]
        self.list.controls = [self._tile(g) for g in goals] or [empty_text("Henüz hedef yok.")]
        self.page.update()

    def _tile(self, g):
        return ft.ListTile(
            title=ft.Text(g["name"]),
            subtitle=ft.Column(
                [
                    ft.Text(f"{fmt_money(g['current_amount'])} / {fmt_money(g['target_amount'])} · %{g['progress_percent']}"
                            f" · {label(GOAL_STATUSES, g['status'])}"),
                    ft.ProgressBar(value=g["progress_percent"] / 100),
                ],
                tight=True,
            ),
            on_click=lambda e, g=g: self.state.router.push(GoalDetail(self.state, g, on_changed=self.refresh).view),
        )

    def _open_form(self, goal):
        self.state.router.push(goal_form(self.state, goal, on_saved=self.refresh))


class GoalDetail:
    """Goal summary + contributions (deposits/withdrawals)."""

    def __init__(self, state, goal, on_changed):
        self.state = state
        self.page = state.page
        self.goal = goal
        self.on_changed = on_changed
        self.summary = ft.Text()
        self.progress = ft.ProgressBar()
        self.list = ft.ListView(expand=True)
        self.view = ft.View(
            route="/goal",
            appbar=ft.AppBar(
                title=ft.Text(goal["name"]),
                actions=[ft.IconButton(ft.Icons.EDIT, on_click=lambda e: self._edit())],
            ),
            floating_action_button=ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda e: self._add_dialog()),
            controls=[self.summary, self.progress, ft.Text("Hareketler", weight=ft.FontWeight.BOLD), self.list],
            padding=16,
        )
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        self.goal = await self.state.budget.goals.get(self.goal["id"])
        rows = (await self.state.budget.contributions.list(goal=self.goal["id"], page_size=100))["results"]
        g = self.goal
        target = f" · Hedef tarih: {fmt_date(g['target_date'])}" if g["target_date"] else ""
        self.summary.value = f"{fmt_money(g['current_amount'])} / {fmt_money(g['target_amount'])} (%{g['progress_percent']}){target}"
        self.progress.value = g["progress_percent"] / 100
        self.list.controls = [self._tile(c) for c in rows] or [empty_text("Henüz hareket yok.")]
        self.page.update()

    def _tile(self, c):
        deposit = Decimal(c["amount"]) > 0
        return ft.ListTile(
            title=ft.Text(("+" if deposit else "") + fmt_money(c["amount"]),
                          color=ft.Colors.GREEN_700 if deposit else ft.Colors.RED_700),
            subtitle=ft.Text(" · ".join(filter(None, [fmt_date(c["date"]), c["note"]]))),
            trailing=ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=lambda e, c=c: confirm(
                self.page, "Bu hareket silinecek.", lambda: self._delete(c))),
        )

    async def _delete(self, c):
        await self.state.budget.contributions.delete(c["id"])
        await self._changed()

    async def _changed(self):
        await self.refresh()
        await self.on_changed()

    def _add_dialog(self):
        page = self.page
        direction = dropdown("İşlem", [("in", "Para ekle"), ("out", "Para çek")], "in")
        amount = money_field("Tutar")
        day = DateInput(page, "Tarih", date.today())
        note = text_field("Not")

        async def save():
            value = parse_money(amount.value)
            if direction.value == "out":
                value = f"-{value}"
            await self.state.budget.contributions.create(
                {"goal": self.goal["id"], "amount": value, "date": day.iso, "note": note.value}
            )
            page.pop_dialog()
            await self._changed()

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Hedef hareketi"),
                content=ft.Column([direction, amount, day.control, note], tight=True),
                actions=[
                    ft.TextButton("Vazgeç", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton("Kaydet", on_click=guarded(page, save)),
                ],
            )
        )

    def _edit(self):
        async def after_save():
            await self._changed()

        async def after_delete():
            self.state.router.pop()  # leave detail view too
            await self.on_changed()

        self.state.router.push(goal_form(self.state, self.goal, on_saved=after_save, on_deleted=after_delete))


def goal_form(state, g: dict | None, on_saved, on_deleted=None) -> ft.View:
    g = g or {}
    page = state.page
    is_edit = bool(g.get("id"))
    name = text_field("Ad", g.get("name"))
    target_amount = money_field("Hedef tutar", g.get("target_amount"))
    target_date = DateInput(page, "Hedef tarih (opsiyonel)", g.get("target_date"), optional=True)
    status = dropdown("Durum", GOAL_STATUSES, g.get("status", "active"))
    note = text_field("Not", g.get("note"), multiline=True)

    async def save():
        if not name.value:
            raise FormError("Ad gerekli.")
        payload = {
            "name": name.value,
            "target_amount": parse_money(target_amount.value),
            "target_date": target_date.iso,
            "status": status.value,
            "note": note.value,
        }
        if is_edit:
            await state.budget.goals.update(g["id"], payload)
        else:
            await state.budget.goals.create(payload)
        state.router.pop()
        await on_saved()

    async def delete():
        await state.budget.goals.delete(g["id"])
        state.router.pop()
        await (on_deleted or on_saved)()

    controls = [name, target_amount, target_date.control] + ([status] if is_edit else []) + [note]
    return form_view(
        state, "/goal-form", "Hedefi düzenle" if is_edit else "Yeni hedef", controls,
        on_save=save, on_delete=delete if is_edit else None,
        delete_message="Hedef ve tüm hareketleri silinecek.",
    )
