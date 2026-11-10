"""
Demo data for looking at the UI: a separate demo user (app "saving") with ~6 months of realistic activity.

    python manage.py seed_demo_data                 # creates/refreshes user "demo" (password Demo-12345)
    python manage.py seed_demo_data --username ali --password 'Sifre-123'

Re-running wipes and rebuilds that user's budget/investment data. Other users are never touched.
Asset prices are not faked: past months without stored prices are valued at cost in the wealth report.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.utils import timezone

from accounts.models import ClientApp, User
from saving_budget.models import (
    Account, Category, Kind, MerchantCategoryRule, Series, StatementImport, Transaction,
)
from saving_budget.services import (
    create_default_categories, create_entry, ensure_category, mark_paid, settle_auto_pay,
)
from saving_invest.models import Asset, Deposit, Trade
from saving_invest.services import (
    close_deposit, default_maturity_amount, sync_assets, sync_deposit_open, sync_trade_entry,
)

D = Decimal


def month_start(d: date, back: int) -> date:
    index = d.year * 12 + d.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


class Command(BaseCommand):
    help = "Create (or rebuild) a demo user with ~6 months of budget and investment data."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--email", default=None)
        parser.add_argument("--password", default="Demo-12345")
        parser.add_argument("--months", type=int, default=6)

    @db_transaction.atomic
    def handle(self, *args, username, email, password, months, **options):
        try:
            app = ClientApp.objects.get(slug="saving")
        except ClientApp.DoesNotExist:
            raise CommandError("ClientApp 'saving' not found (run create_client_app first).")
        user = User.objects.filter(username=username.lower(), app=app).first()
        if user is None:
            user = User.objects.create_user(username.lower(), email or f"{username.lower()}@example.com", password,
                                            app=app, first_name="Demo", last_name="Kullanıcı")
        else:
            user.set_password(password)
            user.save(update_fields=["password"])
            self._wipe(user)
        create_default_categories(user)
        self.user, self.rng = user, random.Random(42)
        self.today = timezone.localdate()
        self.start = month_start(self.today, months - 1)

        self._accounts()
        self._plans()
        self._daily_spending()
        self._settle_past()
        self._investments()
        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: login '{user.username}' / '{password}' (app saving). "
            f"{Transaction.objects.filter(user=user).count()} transactions, "
            f"{Trade.objects.filter(user=user).count()} trades, {Deposit.objects.filter(user=user).count()} deposits."))

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _wipe(user):
        Trade.objects.filter(user=user).delete()
        Deposit.objects.filter(user=user).update(previous=None)
        Deposit.objects.filter(user=user).delete()
        StatementImport.objects.filter(user=user).delete()
        Transaction.objects.filter(user=user).delete()
        Series.objects.filter(user=user).delete()
        Account.objects.filter(user=user).delete()
        MerchantCategoryRule.objects.filter(user=user).delete()
        Category.objects.filter(user=user).delete()

    def cat(self, name, kind=Kind.EXPENSE):
        return ensure_category(self.user, kind, name)

    def add(self, kind, amount, day, description, category, account, repeat="none", card=False, auto=False, **series):
        if day > self.today + timedelta(days=40):
            return None
        return create_entry(user=self.user, repeat=repeat, series_options=series, data={
            "kind": kind, "amount": D(amount).quantize(D("0.01")), "date": day, "description": description,
            "category": self.cat(category, kind), "account": account, "auto_pay": auto, "is_card": card,
        })

    def days(self):
        """Every day from the start to today."""
        d = self.start
        while d <= self.today:
            yield d
            d += timedelta(days=1)

    # ---------------------------------------------------------------- data
    def _accounts(self):
        mk = lambda **kw: Account.objects.create(user=self.user, **kw)  # noqa: E731
        self.salary = mk(name="Ziraat Maaş", account_type="bank", opening_balance=D("18000"))
        self.card = mk(name="Enpara", account_type="bank", opening_balance=D("6500"), statement_day=15,
                       card_name="Enpara Kredi Kartı")
        self.cash = mk(name="Cüzdan", account_type="cash", opening_balance=D("1500"))

    def _plans(self):
        s = self.start
        self.add(Kind.INCOME, 68000, s, "Maaş", "Maaş", self.salary, "recurring", auto=True, frequency="monthly")
        self.add(Kind.EXPENSE, 24000, s.replace(day=5), "Kira", "Kira", self.salary, "recurring", auto=True,
                 frequency="monthly")
        self.add(Kind.EXPENSE, 1350, s.replace(day=20), "Elektrik", "Faturalar", self.salary, "recurring",
                 frequency="monthly")
        self.add(Kind.EXPENSE, 480, s.replace(day=3), "Su", "Faturalar", self.salary, "recurring", frequency="monthly")
        self.add(Kind.EXPENSE, 549, s.replace(day=12), "İnternet", "Faturalar", self.card, "recurring", card=True,
                 auto=True, frequency="monthly")
        self.add(Kind.EXPENSE, 229.99, s.replace(day=18), "Netflix", "Abonelikler", self.card, "recurring", card=True,
                 auto=True, frequency="monthly")
        self.add(Kind.EXPENSE, 1750, s.replace(day=2), "Spor salonu", "Kişisel Bakım", self.card, "recurring",
                 card=True, auto=True, frequency="monthly")
        fridge = month_start(self.today, 3).replace(day=8)
        self.add(Kind.EXPENSE, 36000, fridge, "Buzdolabı", "Ev & Elektronik", self.card, "installment", card=True,
                 auto=True, installment_count=6)

    def _daily_spending(self):
        r = self.rng
        shops = {
            "Market": (["Migros", "A101", "BİM", "Şok", "CarrefourSA"], 250, 2400, 0.45),
            "Yeme-İçme": (["Kahve Dünyası", "Simit Sarayı", "Yemeksepeti", "Burger King", "Köfteci Yusuf"], 120, 950, 0.40),
            "Ulaşım": (["İstanbulkart dolum", "Shell", "Opet", "BiTaksi"], 100, 1800, 0.22),
            "Online Alışveriş": (["Trendyol", "Hepsiburada", "Amazon"], 300, 3500, 0.07),
            "Eğlence": (["Sinema", "Konser bileti", "Bowling"], 250, 1600, 0.05),
            "Giyim": (["LC Waikiki", "Koton", "Zara"], 600, 4200, 0.04),
            "Sağlık": (["Eczane", "Diş kliniği"], 150, 3000, 0.03),
        }
        for day in self.days():
            for category, (names, low, high, chance) in shops.items():
                if r.random() < chance:
                    amount = round(r.uniform(low, high), 2)
                    on_card = category != "Market" or r.random() < 0.6
                    account = self.card if on_card else (self.cash if r.random() < 0.5 else self.salary)
                    self.add(Kind.EXPENSE, amount, day, r.choice(names), category, account,
                             card=account is self.card)
            if day.day == 10:  # cash for the wallet
                self.add(Kind.EXPENSE, 3000, day, "ATM nakit çekim", "Nakit Çekim", self.salary)
                self.add(Kind.INCOME, 3000, day, "ATM nakit çekim", "Gelen Transfer", self.cash)
            if day.day == 25 and r.random() < 0.5:
                self.add(Kind.INCOME, r.choice([6000, 8500, 12000]), day, "Serbest çalışma", "Ek Gelir", self.salary)
        if self.today.day > 3:
            self.add(Kind.INCOME, 750, self.today.replace(day=2), "İade - Trendyol", "İade", self.card, card=True)

    def _settle_past(self):
        """Auto-pay plans settle themselves; mark other past rows paid, but leave this month's water bill overdue."""
        settle_auto_pay(self.today, user=self.user)
        for txn in Transaction.objects.filter(user=self.user, status=Transaction.Status.PENDING, date__lt=self.today):
            if txn.description == "Su" and txn.date.month == self.today.month and txn.date.year == self.today.year:
                continue  # one overdue row to show
            mark_paid(txn, paid_on=txn.date)

    def _investments(self):
        sync_assets()
        assets = {a.code: a for a in Asset.objects.all()}
        t = self.today

        def trade(code, side, qty, price=None, back_days=0, account=None, proceeds=None):
            obj = Trade.objects.create(user=self.user, asset=assets[code], side=side, quantity=D(qty),
                                       unit_price=D(price) if price else None, proceeds=D(proceeds) if proceeds else None,
                                       date=t - timedelta(days=back_days), account=account)
            sync_trade_entry(obj)

        trade("GOLD_GRAM", "buy", "10", "5650", 150, self.salary)
        trade("GOLD_GRAM", "buy", "5", "6050", 80, self.salary)
        trade("GOLD_QUARTER", "buy", "2", "9900", 60)
        trade("USD", "buy", "1500", "46.20", 120, self.salary)
        trade("EUR", "buy", "500", "53.10", 45)
        trade("SILVER_GRAM", "buy", "250", "71.5", 30, self.card)
        trade("GOLD_GRAM", "reduce", "3", back_days=12, account=self.salary, proceeds="19500")

        def deposit(name, principal, rate, start_back, term, account):
            start = t - timedelta(days=start_back)
            end = start + timedelta(days=term)
            obj = Deposit.objects.create(
                user=self.user, name=name, principal=D(principal), annual_rate=D(rate), start_date=start,
                maturity_date=end, maturity_amount=default_maturity_amount(D(principal), D(rate), start, end),
                account=account)
            sync_deposit_open(obj)
            return obj

        closed = deposit("Ziraat 32 gün", "50000", "48", 95, 32, self.salary)
        close_deposit(closed, account=self.salary, on=closed.maturity_date)
        deposit("Enpara 32 gün", "30000", "46", 40, 32, self.card)  # matured: renew or close
        deposit("Ziraat 32 gün", "80000", "45", 10, 32, self.salary)  # active
