"""Investments: portfolio (gold/silver/currency holdings + time deposits), prices, purchases/reductions, deposits."""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import flet as ft

from .choices import DEPOSIT_STATUSES, label
from .theme import (
    CHART, EXPENSE, INCOME, MUTED, asset_badge, card, donut, dot, grouped, icon_badge, muted, section,
)
from .transactions import account_options
from .ui import (
    DateInput, FormError, confirm, dropdown, dropdown_value, empty_text, fmt_date, fmt_money, fmt_number, fmt_pct,
    form_view, guarded, money_field, money_input_value, parse_decimal, parse_money, text_field,
)

GREEN, RED, GREY = INCOME, EXPENSE, MUTED


def _signed_color(value):
    if value in (None, ""):
        return None
    number = Decimal(str(value))
    return GREEN if number > 0 else RED if number < 0 else None


def _section(text):
    return ft.Container(ft.Text(text, weight=ft.FontWeight.W_600, size=16), padding=ft.Padding.only(top=8))


def _line(text, value, bold=False, color=None):
    weight = ft.FontWeight.W_700 if bold else None
    return ft.Row([ft.Text(text, weight=weight, expand=True), ft.Text(fmt_money(value), weight=weight, color=color)])


def _detail(text, color=None):
    return ft.Text(text, size=12, color=color or GREY)


def _qty(value, asset) -> str:
    return f"{fmt_number(value, asset['quantity_decimals'] or 0)} {asset['unit']}"


def _price(value) -> str:
    return fmt_number(value, 4) + " ₺"


def _account_dropdown(state, label_text, none_text, value=None):
    return dropdown(label_text, account_options(state, value), value, with_none=True, none_text=none_text)


def _value_column(value, sub, sub_color=None):
    return ft.Column([ft.Text(value, weight=ft.FontWeight.W_600), ft.Text(sub, size=12, color=sub_color or GREY)],
                     horizontal_alignment=ft.CrossAxisAlignment.END, spacing=0, tight=True)


# ---------------------------------------------------------------- tab
class InvestTab:
    """Total value, allocation ring, holdings, active deposits and current prices (adding: central + menu)."""

    title = "Yatırımlar"

    def __init__(self, state):
        self.state = state
        self.page = state.page
        self.assets = []
        self.body = ft.Column(spacing=12)
        self.control = ft.ListView([self.body], expand=True, padding=ft.Padding.only(left=16, right=16, bottom=96))
        self.fab = None

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        invest = self.state.invest
        p, self.assets, deposits = await asyncio.gather(
            invest.portfolio(), invest.assets(), invest.deposits.list(status="active", page_size=100))
        deposits = deposits["results"]
        t = p["totals"]

        rows = [self._hero(t), *self._allocation(p["items"], t)]
        rows.append(_section("Varlıklarım"))
        rows += grouped([self._position_tile(i) for i in p["items"]],
                        card(muted("Henüz varlık yok. + > Altın / döviz ile alış ekleyin.")))
        if p["items"]:
            gain = f"{fmt_money(t['assets_gain'])} ({fmt_pct(t['assets_gain_pct'])})"
            rows.append(_detail(f"Maliyet {fmt_money(t['assets_cost'])} · Fark {gain}", _signed_color(t["assets_gain"])))

        rows.append(section("Vadeli mevduat", "Geçmiş",
                            lambda e: self.state.router.push(DepositHistoryView(self.state, self.refresh).view)))
        rows += grouped([deposit_tile(self.state, d, self.refresh) for d in deposits],
                        card(muted("Aktif vadeli mevduat yok. + > Vadeli mevduat ile ekleyin.")))
        if deposits:
            rows.append(_detail(f"Anapara {fmt_money(t['deposits_principal'])} · "
                                f"Vade sonu toplamı {fmt_money(t['deposits_at_maturity'])}"))

        rows.append(_section("Güncel fiyatlar"))
        rows += grouped([self._price_tile(a) for a in self.assets])
        self.body.controls = rows
        self.page.update()

    @staticmethod
    def _hero(t):
        on = ft.Colors.ON_PRIMARY
        gain = Decimal(t["assets_gain"])
        hero = card(ft.Column([
            ft.Text("Toplam yatırım değeri", size=13, color=on, opacity=0.85),
            ft.Text(fmt_money(t["total_value"]), size=30, weight=ft.FontWeight.W_700, color=on),
            ft.Text(f"Altın/döviz {fmt_money(t['assets_value'])} · Mevduat {fmt_money(t['deposits_value'])}",
                    size=13, color=on, opacity=0.85),
            ft.Text(("▲ " if gain >= 0 else "▼ ") + f"{fmt_money(abs(gain))} ({fmt_pct(t['assets_gain_pct'])}) "
                    "maliyete göre", size=12, color=on, opacity=0.85),
        ], spacing=6), padding=20, bgcolor=ft.Colors.PRIMARY, radius=22)
        hero.expand = True
        return ft.Row([hero])

    @staticmethod
    def _allocation(items, t):
        parts = [(i["asset"]["name"], Decimal(i["value"] or i["cost"])) for i in items]
        if Decimal(t["deposits_value"]):
            parts.append(("Vadeli mevduat", Decimal(t["deposits_value"])))
        total = sum((v for _, v in parts), Decimal(0))
        if not total:
            return []
        colors = [CHART[i % (len(CHART) - 1)] for i in range(len(parts))]
        legend = ft.Column([
            ft.Row([dot(c), ft.Text(name, size=13, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(f"%{fmt_number(value / total * 100, 0)}", size=13, weight=ft.FontWeight.W_600)], spacing=8)
            for (name, value), c in zip(parts, colors)
        ], spacing=8, expand=True)
        ring = donut([(float(v), c) for (_, v), c in zip(parts, colors)], center_top="dağılım",
                     center_bottom=f"{len(parts)} kalem")
        return [card(ft.Column([section("Dağılım"), ft.Row([ring, legend], spacing=16,
                                                           vertical_alignment=ft.CrossAxisAlignment.CENTER)],
                               spacing=10))]

    def _open_asset(self, code):
        asset = next(a for a in self.assets if a["code"] == code)
        self.state.router.push(AssetView(self.state, asset, self.refresh).view)

    def _position_tile(self, item):
        asset = item["asset"]
        sub = f"{_qty(item['quantity'], asset)} · ort. {_price(item['average_cost'])}"
        if not item["price"]:
            sub += " · fiyat yok"
        return ft.ListTile(
            leading=asset_badge(asset), title=ft.Text(asset["name"], weight=ft.FontWeight.W_500),
            subtitle=ft.Text(sub, color=GREY),
            trailing=_value_column(fmt_money(item["value"] or item["cost"]), fmt_pct(item["gain_pct"]),
                                   _signed_color(item["gain"])),
            on_click=lambda e: self._open_asset(asset["code"]),
        )

    def _price_tile(self, a):
        price = a["price"]
        sub = f"Satış {_price(price['sell'])} · {fmt_date(price['date'])}" if price else "Henüz fiyat alınmadı"
        return ft.ListTile(
            leading=asset_badge(a, size=36), title=ft.Text(a["name"], weight=ft.FontWeight.W_500),
            subtitle=ft.Text(sub, size=12, color=GREY),
            trailing=_value_column(_price(price["buy"]) if price else "—", fmt_pct(a["change_pct"]),
                                   _signed_color(a["change_pct"])),
            on_click=lambda e: self._open_asset(a["code"]),
        )


# ---------------------------------------------------------------- asset detail + trades
class AssetView:
    """One asset: holding, recent prices, purchases/reductions (tap to edit)."""

    def __init__(self, state, asset, on_changed):
        self.state = state
        self.page = state.page
        self.asset = asset
        self.on_changed = on_changed
        self.held = Decimal(0)
        self.header = ft.Column(spacing=4)
        self.list = ft.Column(spacing=0)
        self.reduce_button = ft.OutlinedButton("Azalt", icon=ft.Icons.REMOVE,
                                               on_click=lambda e: self._open_form("reduce", None))
        self.view = ft.View(
            route="/asset",
            appbar=ft.AppBar(title=ft.Text(asset["name"])),
            controls=[ft.ListView([
                card(ft.Row([asset_badge(asset, size=48), self.header], spacing=14,
                            vertical_alignment=ft.CrossAxisAlignment.START)),
                ft.Row([ft.FilledButton("Alış ekle", icon=ft.Icons.ADD, on_click=lambda e: self._open_form("buy", None)),
                        self.reduce_button], wrap=True),
                _section("İşlemler"),
                self.list,
            ], expand=True, padding=16, spacing=12)],
            padding=0,
        )
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        a, invest = self.asset, self.state.invest
        portfolio = await invest.portfolio()
        item = next((i for i in portfolio["items"] if i["asset"]["code"] == a["code"]), None)
        trades = (await invest.trades.list(asset=a["code"], page_size=100))["results"]
        history = await invest.history(a["code"], days=30)
        self.held = Decimal(item["quantity"]) if item else Decimal(0)
        self.reduce_button.disabled = self.held <= 0

        rows = [ft.Text(f"Elimdeki: {_qty(self.held, a)}", size=18, weight=ft.FontWeight.W_700)]
        if item:
            rows += [_detail(f"Ortalama maliyet {_price(item['average_cost'])} · Maliyet {fmt_money(item['cost'])}"),
                     _detail(f"Bugünkü değer {fmt_money(item['value'] or item['cost'])} · Fark {fmt_money(item['gain'] or 0)} "
                             f"({fmt_pct(item['gain_pct'])})", _signed_color(item["gain"]))]
        if a["price"]:
            rows.append(_detail(f"Fiyat: alış {_price(a['price']['buy'])} · satış {_price(a['price']['sell'])} "
                                f"({fmt_date(a['price']['date'])})"))
        if history:
            buys = [Decimal(h["buy"]) for h in history]
            rows.append(_detail(f"Son 30 gün alış fiyatı: en düşük {_price(min(buys))} · en yüksek {_price(max(buys))} "
                                f"({len(history)} gün)"))
        self.header.controls = rows
        self.list.controls = grouped([self._trade_tile(t) for t in trades], card(muted("Henüz işlem yok.")))
        self.page.update()

    def _trade_tile(self, t):
        a = t["asset_info"]
        if t["side"] == "buy":
            title = f"Alış · {_qty(t['quantity'], a)}"
            parts = [f"{_price(t['unit_price'])} / {a['unit']}", f"toplam {fmt_money(t['total'])}"]
            if t["account"]:
                parts.append(f"{self.state.account_name(t['account'])} hesabından düşüldü")
        else:
            title = f"Azaltma · {_qty(t['quantity'], a)}"
            parts = [f"{fmt_money(t['proceeds'])} {self.state.account_name(t['account'])} hesabına eklendi"
                     if t["proceeds"] else "TL karşılığı eklenmedi"]
        if t["note"]:
            parts.append(t["note"])
        return ft.ListTile(
            leading=ft.Icon(ft.Icons.ADD_CIRCLE if t["side"] == "buy" else ft.Icons.REMOVE_CIRCLE,
                            color=GREEN if t["side"] == "buy" else RED),
            title=ft.Text(title), subtitle=ft.Text(f"{fmt_date(t['date'])} · " + " · ".join(parts)),
            on_click=lambda e: self._open_form(t["side"], t),
        )

    def _open_form(self, side, trade):
        self.state.router.push(trade_form(self.state, [self.asset], self.asset, side, trade, self._changed,
                                          held=self.held))

    async def _changed(self):
        await self.refresh()
        await self.on_changed()


def trade_form(state, assets, asset, side, trade, on_saved, held=None) -> ft.View:
    """
    Purchase or reduction. Purchase: quantity + unit price, optionally deducted from an account.
    Reduction: quantity, optionally the TRY received added to an account. `asset` None -> choose from `assets`.
    """
    page = state.page
    trade = trade or {}
    is_edit = bool(trade)
    is_buy = side == "buy"
    current = {"asset": asset or assets[0]}

    asset_dd = dropdown("Varlık", [(a["code"], a["name"]) for a in assets], current["asset"]["code"])
    asset_dd.visible = asset is None
    quantity = ft.TextField(value=fmt_number(trade["quantity"], 6) if trade else "",
                            keyboard_type=ft.KeyboardType.NUMBER)
    unit_price = ft.TextField(label="Birim fiyat (₺)", keyboard_type=ft.KeyboardType.NUMBER, visible=is_buy)
    proceeds = money_field("Alınan TL tutarı (isteğe bağlı)", trade.get("proceeds"))
    proceeds.visible = not is_buy
    account = _account_dropdown(
        state, "Hesap", "Hesaptan düşülmesin" if is_buy else "Hesaba eklenmesin", trade.get("account"))
    hint = _detail("")
    day = DateInput(page, "Tarih", trade.get("date") or date.today())
    note = text_field("Not", trade.get("note"))

    def apply_asset(prefill_price):
        a = current["asset"]
        quantity.label = f"Miktar ({a['unit']})"
        if is_buy:
            account.label = "Hangi hesaptan ödendi?"
            hint.value = "Hesap seçerseniz toplam tutar o hesaptan \"Yatırım\" gideri olarak düşülür."
            if prefill_price:
                unit_price.value = money_input_value(trade.get("unit_price") or (a["price"] and a["price"]["sell"]))
        else:
            account.label = "TL tutarı hangi hesaba eklensin?"
            hint.value = (f"Elinizde {_qty(held, a)} var. " if held is not None else "") + \
                "Tutar ve hesap girerseniz o hesaba \"Yatırım\" geliri olarak eklenir."

    def asset_changed(e):
        current["asset"] = next(a for a in assets if a["code"] == asset_dd.value)
        apply_asset(prefill_price=True)
        page.update()

    asset_dd.on_select = asset_changed
    apply_asset(prefill_price=True)

    async def save():
        a = current["asset"]
        payload = {
            "asset": a["code"], "side": side, "date": day.iso, "note": note.value or "",
            "quantity": parse_decimal(quantity.value, "Miktar", a["quantity_decimals"]),
            "account": dropdown_value(account),
        }
        if is_buy:
            payload["unit_price"] = parse_decimal(unit_price.value, "Birim fiyat", 4)
        else:
            payload["proceeds"] = parse_money(proceeds.value) if (proceeds.value or "").strip() else None
            if payload["proceeds"] and not payload["account"]:
                raise FormError("TL tutarın ekleneceği hesabı seçin.")
            if payload["account"] and not payload["proceeds"]:
                raise FormError("Hesaba eklenecek TL tutarını girin.")
        if is_edit:
            await state.invest.trades.update(trade["id"], payload)
        else:
            await state.invest.trades.create(payload)
        state.router.pop()
        await on_saved()

    async def delete():
        await state.invest.trades.delete(trade["id"])
        state.router.pop()
        await on_saved()

    title = ("Alışı düzenle" if is_edit else "Alış ekle") if is_buy else ("Azaltmayı düzenle" if is_edit else "Azalt")
    return form_view(state, "/trade", title,
                     [asset_dd, quantity, unit_price, day.control, proceeds, account, hint, note],
                     on_save=save, on_delete=delete if is_edit else None,
                     delete_message="Bu işlem silinecek. Bütçeye yazılan karşılığı da silinir.")


# ---------------------------------------------------------------- deposits
def deposit_tile(state, d, on_changed) -> ft.ListTile:
    parts = [f"{fmt_money(d['principal'])} → {fmt_money(d['maturity_amount'])}", f"%{fmt_number(d['annual_rate'], 4)}",
             f"vade {fmt_date(d['maturity_date'])}"]
    color = None
    if d["status"] == "active":
        if d["is_matured"]:
            parts.append("Vadesi doldu: yenileyin veya kapatın")
            color = RED
        else:
            parts.append(f"{d['days_left']} gün kaldı")
    else:
        parts.append(label(DEPOSIT_STATUSES, d["status"]))
    value = d["current_value"] if d["status"] == "active" else (d["close_amount"] or d["maturity_amount"])
    return ft.ListTile(
        leading=icon_badge(ft.Icons.ACCOUNT_BALANCE, "#DC2626" if color else "#6D28D9"),
        title=ft.Text(d["name"], weight=ft.FontWeight.W_500), subtitle=ft.Text(" · ".join(parts), color=color or GREY),
        trailing=ft.Text(fmt_money(value), weight=ft.FontWeight.W_600),
        on_click=lambda e: state.router.push(DepositView(state, d, on_changed).view),
    )


class DepositView:
    """Deposit details + actions: edit / renew / close (active), reopen (closed), delete."""

    def __init__(self, state, deposit, on_changed):
        self.state = state
        self.page = state.page
        self.on_changed = on_changed
        d = deposit
        self.d = d
        lines = [
            ("Anapara", fmt_money(d["principal"])),
            ("Yıllık faiz", f"%{fmt_number(d['annual_rate'], 4)}"),
            ("Başlangıç", fmt_date(d["start_date"])),
            ("Vade sonu", f"{fmt_date(d['maturity_date'])} ({d['term_days']} gün)"),
            ("Vade sonu tutarı", fmt_money(d["maturity_amount"])),
            ("Faiz getirisi", fmt_money(d["interest"])),
            ("Durum", label(DEPOSIT_STATUSES, d["status"]) + (" · vadesi doldu" if d["is_matured"] else "")),
        ]
        if d["status"] == "active":
            lines.append(("Bugünkü değer", fmt_money(d["current_value"])))
        if d["account"]:
            lines.append(("Açılışta düşülen hesap", state.account_name(d["account"])))
        if d["status"] == "closed":
            lines.append(("Kapanış", f"{fmt_date(d['closed_on'])} · {fmt_money(d['close_amount'])}"
                          + (f" → {state.account_name(d['close_account'])}" if d["close_account"] else "")))
        if d["note"]:
            lines.append(("Not", d["note"]))

        buttons = []
        if d["status"] == "active":
            buttons += [
                ft.OutlinedButton("Düzenle", icon=ft.Icons.EDIT,
                                  on_click=lambda e: state.router.push(deposit_form(state, d, self._done))),
                ft.FilledButton("Yenile", icon=ft.Icons.AUTORENEW,
                                on_click=lambda e: state.router.push(renew_form(state, d, self._done))),
                ft.OutlinedButton("Kapat", icon=ft.Icons.CHECK,
                                  on_click=lambda e: state.router.push(close_form(state, d, self._done))),
            ]
        elif d["status"] == "closed":
            buttons.append(ft.OutlinedButton("Yeniden aç (kapanışı geri al)", icon=ft.Icons.UNDO,
                                             on_click=guarded(self.page, self._reopen)))
        if d["status"] == "active" and d["is_matured"]:
            info = "Vadesi doldu. Yeni oran ve vadeyle yenileyebilir ya da kapatıp tutarı bir hesaba ekleyebilirsiniz."
        else:
            info = ""
        self.view = ft.View(
            route="/deposit",
            appbar=ft.AppBar(title=ft.Text(d["name"]), actions=[ft.IconButton(
                ft.Icons.DELETE, on_click=lambda e: confirm(
                    self.page, "Mevduat silinecek. Bütçeye yazılan açılış/kapanış kayıtları da silinir.", self._delete))]),
            controls=[ft.ListView([
                card(ft.Column([ft.Row([ft.Text(k, expand=True, color=GREY), ft.Text(v, weight=ft.FontWeight.W_600)])
                                for k, v in lines], spacing=10)),
                _detail(info, RED) if info else ft.Container(),
                ft.Row(buttons, wrap=True),
            ], expand=True, padding=16, spacing=8)],
            padding=0,
        )

    async def _done(self):
        self.state.router.pop()  # the detail view shows stale data; go back to the refreshed list
        await self.on_changed()

    async def _reopen(self):
        await self.state.invest.deposits.reopen(self.d["id"])
        await self._done()

    async def _delete(self):
        await self.state.invest.deposits.delete(self.d["id"])
        await self._done()


def deposit_form(state, d: dict | None, on_saved) -> ft.View:
    page = state.page
    d = d or {}
    is_edit = bool(d)
    name = text_field("Ad (ör. Enpara 32 gün)", d.get("name"))
    principal = money_field("Anapara (₺)", d.get("principal"))
    rate = ft.TextField(label="Yıllık faiz oranı (%)", value=fmt_number(d["annual_rate"], 4) if d else "",
                        keyboard_type=ft.KeyboardType.NUMBER)
    start = DateInput(page, "Başlangıç tarihi", d.get("start_date") or date.today())
    end = DateInput(page, "Vade sonu tarihi", d.get("maturity_date") or date.today() + timedelta(days=32))
    maturity = money_field("Vade sonu tutarı (₺)", d.get("maturity_amount"))
    account = _account_dropdown(state, "Anapara hangi hesaptan çıktı?", "Hesaptan düşülmesin", d.get("account"))
    note = text_field("Not", d.get("note"))

    async def save():
        if not (name.value or "").strip():
            raise FormError("Ad gerekli.")
        if not end.iso or not start.iso or end.value <= start.value:
            raise FormError("Vade sonu başlangıçtan sonra olmalı.")
        payload = {
            "name": name.value.strip(), "principal": parse_money(principal.value),
            "annual_rate": parse_decimal(rate.value, "Faiz oranı", 4),
            "start_date": start.iso, "maturity_date": end.iso, "account": dropdown_value(account), "note": note.value or "",
        }
        if (maturity.value or "").strip():
            payload["maturity_amount"] = parse_money(maturity.value)
        if is_edit:
            await state.invest.deposits.update(d["id"], payload)
        else:
            await state.invest.deposits.create(payload)
        state.router.pop()
        await on_saved()

    return form_view(state, "/deposit-form", "Mevduatı düzenle" if is_edit else "Vadeli mevduat ekle", [
        name, principal, rate, start.control, end.control, maturity,
        _detail("Vade sonu tutarını bankanın verdiği net tutarla girin. Boş bırakırsanız faiz oranından hesaplanır "
                "(stopaj düşülerek)."),
        account, _detail("Hesap seçerseniz anapara başlangıç tarihinde o hesaptan düşülür."), note,
    ], on_save=save)


def close_form(state, d, on_saved) -> ft.View:
    page = state.page
    amount = money_field("Alınan tutar (₺)", d["maturity_amount"])
    account = _account_dropdown(state, "Tutar hangi hesaba eklensin?", "Hesaba eklenmesin")
    on = DateInput(page, "Kapanış tarihi", min(date.today(), date.fromisoformat(d["maturity_date"])))

    async def save():
        await state.invest.deposits.close(d["id"], account=dropdown_value(account), amount=parse_money(amount.value),
                                          date=on.iso)
        state.router.pop()
        await on_saved()

    return form_view(state, "/deposit-close", f"Kapat: {d['name']}", [
        amount, on.control, account, _detail("Hesap seçerseniz tutar o hesaba \"Yatırım\" geliri olarak eklenir."),
    ], on_save=save)


def renew_form(state, d, on_saved) -> ft.View:
    page = state.page
    old_end = date.fromisoformat(d["maturity_date"])
    rate = ft.TextField(label="Yeni yıllık faiz oranı (%)", value=fmt_number(d["annual_rate"], 4),
                        keyboard_type=ft.KeyboardType.NUMBER)
    end = DateInput(page, "Yeni vade sonu", old_end + timedelta(days=d["term_days"]))
    maturity = money_field("Yeni vade sonu tutarı (₺)")
    name = text_field("Ad", d["name"])

    async def save():
        if not end.value or end.value <= old_end:
            raise FormError("Yeni vade sonu eski vade sonundan sonra olmalı.")
        data = {"annual_rate": parse_decimal(rate.value, "Faiz oranı", 4), "maturity_date": end.iso,
                "name": (name.value or "").strip() or None}
        if (maturity.value or "").strip():
            data["maturity_amount"] = parse_money(maturity.value)
        await state.invest.deposits.renew(d["id"], data)
        state.router.pop()
        await on_saved()

    return form_view(state, "/deposit-renew", f"Yenile: {d['name']}", [
        _detail(f"Yeni anapara: {fmt_money(d['maturity_amount'])} (eski vade sonu tutarı) · "
                f"başlangıç {fmt_date(d['maturity_date'])}"),
        rate, end.control, maturity, _detail("Vade sonu tutarı boş bırakılırsa faiz oranından hesaplanır (stopaj düşülerek)."),
        name,
    ], on_save=save)


class DepositHistoryView:
    """Renewed and closed deposits."""

    def __init__(self, state, on_changed):
        self.state = state
        self.page = state.page
        self.on_changed = on_changed
        self.list = ft.ListView(expand=True, padding=16)
        self.view = ft.View(route="/deposit-history", appbar=ft.AppBar(title=ft.Text("Geçmiş mevduatlar")),
                            controls=[self.list], padding=0)
        self.page.run_task(self.refresh)

    async def refresh(self):
        await guarded(self.page, self._fetch)()

    async def _fetch(self):
        rows = (await self.state.invest.deposits.list(status="renewed,closed", page_size=100))["results"]
        rows.sort(key=lambda d: d["maturity_date"], reverse=True)
        self.list.controls = grouped([deposit_tile(self.state, d, self._changed) for d in rows], empty_text("Kayıt yok."))
        self.page.update()

    async def _changed(self):
        await self.refresh()
        await self.on_changed()
