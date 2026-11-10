import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from saving_budget.models import Kind
from saving_budget.services import sync_linked_entry

from .catalog import ASSETS
from .models import Asset, AssetPrice, Deposit, Trade
from .providers import PROVIDERS

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def pct(part: Decimal, whole: Decimal):
    return (part / whole * 100).quantize(CENT, rounding=ROUND_HALF_UP) if whole else None


# --- catalog & prices ---------------------------------------------------------------------------

def sync_assets() -> int:
    """Upsert catalog rows (idempotent). Assets removed from the catalog are deactivated, not deleted."""
    codes = []
    for order, (code, name, asset_type, unit, decimals, provider, source_code) in enumerate(ASSETS):
        Asset.objects.update_or_create(code=code, defaults={
            "name": name, "asset_type": asset_type, "unit": unit, "quantity_decimals": decimals,
            "provider": provider, "source_code": source_code, "sort_order": order, "is_active": True,
        })
        codes.append(code)
    Asset.objects.exclude(code__in=codes).update(is_active=False)
    return len(codes)


def fetch_prices() -> dict:
    """Fetch current prices from every provider used by active assets; one row per asset and day (upsert)."""
    sync_assets()
    assets = list(Asset.objects.filter(is_active=True))
    saved, failed = 0, []
    for key in sorted({a.provider for a in assets}):
        try:
            quotes = {q.source_code: q for q in PROVIDERS[key]().fetch()}
        except Exception:
            logger.exception("Price provider %s failed.", key)
            failed.append(key)
            continue
        for asset in (a for a in assets if a.provider == key):
            quote = quotes.get(asset.source_code)
            if quote is None:
                logger.warning("Provider %s returned no price for %s.", key, asset.code)
                failed.append(f"{key}:{asset.code}")
                continue
            AssetPrice.objects.update_or_create(asset=asset, date=quote.date, defaults={
                "buy": quote.buy, "sell": quote.sell, "source_time": quote.source_time,
            })
            saved += 1
    return {"saved": saved, "failed": failed}


def latest_prices(assets) -> dict:
    """asset_id -> (latest AssetPrice | None, previous AssetPrice | None)."""
    result = {}
    for asset in assets:
        rows = list(asset.prices.order_by("-date")[:2])
        result[asset.pk] = (rows[0] if rows else None, rows[1] if len(rows) > 1 else None)
    return result


def change_pct(latest, previous):
    """Day-over-day change of the buy price, in percent."""
    if not latest or not previous:
        return None
    return pct(latest.buy - previous.buy, previous.buy)


def price_history(asset, days: int):
    return asset.prices.filter(date__gte=timezone.localdate() - timedelta(days=days)).order_by("date")


# --- holdings -----------------------------------------------------------------------------------

def _order(trade_date, side, created_at):
    """Chronological; on the same day purchases come before reductions."""
    return trade_date, side != Trade.Side.BUY, created_at


def qty_text(quantity: Decimal) -> str:
    return f"{quantity.normalize():f}"


@dataclass
class Position:
    """Average-cost holding: a reduction removes quantity at the average cost (no sale profit is tracked)."""

    asset: Asset
    quantity: Decimal = ZERO
    cost: Decimal = ZERO  # cost basis of the remaining quantity

    def apply(self, trade: Trade):
        if trade.side == Trade.Side.BUY:
            self.quantity += trade.quantity
            self.cost += trade.quantity * trade.unit_price
            return
        average = self.average_cost
        self.quantity -= trade.quantity
        self.cost = ZERO if self.quantity <= 0 else self.cost - average * trade.quantity

    @property
    def average_cost(self) -> Decimal:
        return self.cost / self.quantity if self.quantity > 0 else ZERO


def _replay(trades) -> dict:
    result: dict = {}
    for trade in sorted(trades, key=lambda t: _order(t.date, t.side, t.created_at)):
        result.setdefault(trade.asset_id, Position(trade.asset)).apply(trade)
    return result


def holding_quantity(user, asset) -> Decimal:
    position = _replay(Trade.objects.filter(user=user, asset=asset)).get(asset.pk)
    return position.quantity if position else ZERO


def find_overdraw(user, asset, exclude: Trade | None = None, new: tuple[date, str, Decimal] | None = None):
    """
    Replay the asset's trades without `exclude` and with `new` = (date, side, quantity); return the first date on
    which more is reduced than held, or None. Covers creates, edits (exclude=old, new=changed) and deletes.
    """
    rows = [(t.date, t.side, t.created_at, t.quantity)
            for t in Trade.objects.filter(user=user, asset=asset).exclude(pk=getattr(exclude, "pk", None))]
    if new:
        rows.append((new[0], new[1], exclude.created_at if exclude else timezone.now(), new[2]))
    held = ZERO
    for trade_date, side, _, quantity in sorted(rows, key=lambda r: _order(r[0], r[1], r[2])):
        held += quantity if side == Trade.Side.BUY else -quantity
        if held < 0:
            return trade_date
    return None


def sync_trade_entry(trade: Trade):
    """Mirror the trade in the budget: purchase -> expense of the account, reduction proceeds -> income."""
    label = f"{trade.asset.name} ({qty_text(trade.quantity)} {trade.asset.unit})"
    if trade.side == Trade.Side.BUY:
        kind, amount, description = Kind.EXPENSE, money(trade.quantity * trade.unit_price), f"Alış: {label}"
    else:
        kind, amount, description = Kind.INCOME, trade.proceeds, f"TL'ye çevrildi: {label}"
    entry = sync_linked_entry(trade.budget_entry, user=trade.user, account=trade.account, kind=kind,
                              amount=amount, date=trade.date, description=description)
    if entry != trade.budget_entry:
        trade.budget_entry = entry
        trade.save(update_fields=["budget_entry", "updated_at"])


@db_transaction.atomic
def delete_trade(trade: Trade):
    entry = trade.budget_entry
    trade.delete()
    if entry:
        entry.delete()


# --- time deposits ------------------------------------------------------------------------------

def default_maturity_amount(principal: Decimal, annual_rate: Decimal, start: date, end: date) -> Decimal:
    """Simple interest, 365-day year, net of withholding tax (DEPOSIT_WITHHOLDING_RATE %); the user can adjust it."""
    gross = principal * annual_rate / 100 * (end - start).days / 365
    return money(principal + gross * (1 - settings.DEPOSIT_WITHHOLDING_RATE / 100))


def deposit_value(deposit: Deposit, today: date | None = None) -> Decimal:
    """Today's value of an active deposit: interest accrues linearly from start to maturity."""
    today = today or timezone.localdate()
    term = (deposit.maturity_date - deposit.start_date).days
    if term <= 0:
        return deposit.maturity_amount
    elapsed = min(max((today - deposit.start_date).days, 0), term)
    return money(deposit.principal + (deposit.maturity_amount - deposit.principal) * elapsed / term)


def sync_deposit_open(deposit: Deposit):
    entry = sync_linked_entry(deposit.open_entry, user=deposit.user, account=deposit.account, kind=Kind.EXPENSE,
                              amount=deposit.principal, date=deposit.start_date,
                              description=f"Vadeli mevduat: {deposit.name}")
    if entry != deposit.open_entry:
        deposit.open_entry = entry
        deposit.save(update_fields=["open_entry", "updated_at"])


@db_transaction.atomic
def close_deposit(deposit: Deposit, *, account=None, amount: Decimal | None = None, on: date | None = None) -> Deposit:
    """Close the deposit; with an account, the amount (default: maturity amount) is added to it as income."""
    deposit.status = Deposit.Status.CLOSED
    deposit.closed_on = on or min(timezone.localdate(), deposit.maturity_date)
    deposit.close_amount = amount or deposit.maturity_amount
    deposit.close_account = account
    deposit.close_entry = sync_linked_entry(deposit.close_entry, user=deposit.user, account=account,
                                            kind=Kind.INCOME, amount=deposit.close_amount, date=deposit.closed_on,
                                            description=f"Vadeli mevduat kapanışı: {deposit.name}")
    deposit.save()
    return deposit


@db_transaction.atomic
def reopen_deposit(deposit: Deposit) -> Deposit:
    """Undo a close (e.g. closed by mistake): removes the closing income entry."""
    entry = deposit.close_entry
    deposit.status = Deposit.Status.ACTIVE
    deposit.closed_on = deposit.close_amount = deposit.close_account = deposit.close_entry = None
    deposit.save()
    if entry:
        entry.delete()
    return deposit


@db_transaction.atomic
def renew_deposit(deposit: Deposit, *, annual_rate, maturity_date, maturity_amount=None, name=None) -> Deposit:
    """Roll over at maturity: a new deposit starting at the old maturity date with the old maturity amount."""
    principal, start = deposit.maturity_amount, deposit.maturity_date
    renewal = Deposit.objects.create(
        user=deposit.user, name=name or deposit.name, principal=principal, annual_rate=annual_rate,
        start_date=start, maturity_date=maturity_date, previous=deposit,
        maturity_amount=maturity_amount or default_maturity_amount(principal, annual_rate, start, maturity_date),
    )
    deposit.status = Deposit.Status.RENEWED
    deposit.save(update_fields=["status", "updated_at"])
    return renewal


@db_transaction.atomic
def delete_deposit(deposit: Deposit):
    """Delete with its budget mirrors; deleting a renewal makes the previous deposit active again."""
    entries = [e for e in (deposit.open_entry, deposit.close_entry) if e]
    previous = deposit.previous
    deposit.delete()
    for entry in entries:
        entry.delete()
    if previous and previous.status == Deposit.Status.RENEWED:
        previous.status = Deposit.Status.ACTIVE
        previous.save(update_fields=["status", "updated_at"])


# --- portfolio ----------------------------------------------------------------------------------

def portfolio(user) -> dict:
    """Holdings valued at the latest buy price (what the market pays you) + active deposits; totals in TRY."""
    held = [p for p in _replay(Trade.objects.filter(user=user).select_related("asset")).values() if p.quantity > 0]
    held.sort(key=lambda p: (p.asset.sort_order, p.asset.code))
    prices = latest_prices([p.asset for p in held])
    items, cost, value = [], ZERO, ZERO
    for p in held:
        latest, previous = prices[p.asset.pk]
        row_cost = money(p.cost)
        row_value = money(p.quantity * latest.buy) if latest else None
        gain = row_value - row_cost if row_value is not None else None
        items.append({
            "asset": p.asset, "quantity": p.quantity, "average_cost": p.average_cost.quantize(Decimal("0.0001")),
            "cost": row_cost, "price": latest.buy if latest else None,
            "price_date": latest.date if latest else None, "change_pct": change_pct(latest, previous),
            "value": row_value, "gain": gain, "gain_pct": pct(gain, row_cost) if gain is not None else None,
        })
        cost += row_cost
        value += row_value if row_value is not None else row_cost  # no price yet: count at cost
    deposits = list(Deposit.objects.filter(user=user, status=Deposit.Status.ACTIVE))
    deposits_value = sum((deposit_value(d) for d in deposits), ZERO)
    return {"items": items, "totals": {
        "assets_cost": cost, "assets_value": value, "assets_gain": value - cost, "assets_gain_pct": pct(value - cost, cost),
        "deposits_principal": sum((d.principal for d in deposits), ZERO), "deposits_value": deposits_value,
        "deposits_at_maturity": sum((d.maturity_amount for d in deposits), ZERO),
        "total_value": value + deposits_value,
    }}


