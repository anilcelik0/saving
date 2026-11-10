from dataclasses import dataclass, field

import flet as ft

from router import Router
from services.api_client import ApiClient, ApiError
from services.auth_service import AuthService
from services.budget_service import BudgetService
from services.invest_service import InvestService
from services.report_service import ReportService


@dataclass
class AppState:
    """Shared app state + session lifecycle. Screens receive this object."""

    page: ft.Page
    router: Router
    api: ApiClient = None
    auth: AuthService = None
    budget: BudgetService = None
    invest: InvestService = None
    reports: ReportService = None
    user: dict | None = None
    categories: list = field(default_factory=list)
    accounts: list = field(default_factory=list)

    # --- session ---
    async def start(self):
        if self.api.tokens.has_session:
            try:
                self.user = await self.auth.me()  # refreshes the access token if needed
                await self.enter_app()
                return
            except ApiError:
                pass
        self.show_login()

    async def login(self, identifier, password):
        self.user = await self.auth.login(identifier, password)
        await self.enter_app()

    async def register(self, **fields):
        self.user = await self.auth.register(**fields)
        await self.enter_app()

    async def logout(self):
        await self.auth.logout()
        self.user = None
        self.show_login()

    async def on_session_expired(self):
        self.user = None
        self.show_login(message="Oturumunuzun süresi doldu. Lütfen tekrar giriş yapın.")

    async def enter_app(self):
        from screens.home import HomeScreen

        await self.load_refs()
        self.router.reset(HomeScreen(self).view)

    def show_login(self, message: str | None = None):
        from screens.auth import login_view
        from screens.ui import toast

        self.router.reset(login_view(self))
        if message:
            toast(self.page, message, error=True)

    # --- reference data (categories/accounts) used by forms and list labels ---
    async def load_refs(self):
        self.categories = await self.budget.categories.list(include_archived="true")
        self.accounts = await self.budget.accounts.list(include_archived="true")

    def category_name(self, category_id) -> str:
        return next((c["name"] for c in self.categories if c["id"] == category_id), "Kategorisiz")

    def account_name(self, account_id) -> str:
        return next((a["name"] for a in self.accounts if a["id"] == account_id), "")

    def card_name(self, account_id) -> str:
        account = next((a for a in self.accounts if a["id"] == account_id), None)
        if account is None:
            return "Kart"
        return account.get("card_name") or f"{account['name']} kartı"
