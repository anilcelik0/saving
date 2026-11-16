from dataclasses import dataclass, field

import flet as ft

from router import Router
from services.api_client import ApiClient, ApiError
from services.auth_service import AuthService
from services.budget_service import BudgetService
from services.invest_service import InvestService
from services.settings_store import SettingsStore
from services.report_service import ReportService
from services.support_service import SupportService


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
    settings: SettingsStore = None
    support: SupportService = None
    user: dict | None = None
    home: object = None  # HomeScreen of the current session
    categories: list = field(default_factory=list)
    accounts: list = field(default_factory=list)
    # statements uploaded in this session: id -> (file name, bytes). Kept only in memory on the device so
    # "Sorun bildir" can attach the file (the server deletes it right after parsing).
    statement_files: dict = field(default_factory=dict)

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

    async def end_session(self, message: str):
        """After freezing / requesting deletion: the server already revoked the sessions; forget them here."""
        await self.api.tokens.clear()
        self.user = None
        self.show_login(message=message, error=False)

    async def on_session_expired(self):
        self.user = None
        self.show_login(message="Oturumunuzun süresi doldu. Lütfen tekrar giriş yapın.")

    async def enter_app(self):
        from screens.home import HomeScreen
        from screens.legal import consent_gate_view
        from screens.ui import set_reporter

        set_reporter(lambda error: self.open_report(error=error))  # error toasts offer "Bildir"

        # frozen / deletion-pending account: reopen (or cancel deletion) before anything else
        if (self.user or {}).get("account_status", "active") != "active":
            from screens.account import account_status_view

            self.router.reset(account_status_view(self, self.enter_app))
            return
        # new privacy policy / KVKK versions must be accepted before using the app
        pending = (self.user or {}).get("pending_legal") or []
        if pending:
            self.router.reset(consent_gate_view(self, pending, self._after_consent))
            return
        await self.load_refs()
        self.home = HomeScreen(self)
        self.router.reset(self.home.view)
        if self.settings and not self.settings.is_onboarded(self.user_key):
            self.show_onboarding()

    async def _after_consent(self):
        self.user = await self.auth.me()
        await self.enter_app()

    @property
    def user_key(self) -> str:
        u = self.user or {}
        return str(u.get("id") or u.get("username") or "")

    def show_onboarding(self):
        """App tour; first run per user on this device, or from Diğer > Uygulama turu."""
        from screens.more import account_form
        from screens.onboarding import onboarding_view

        async def finished(add_account: bool):
            if self.settings:
                await self.settings.mark_onboarded(self.user_key)
            self.router.pop()
            if add_account:
                self.router.push(account_form(self, None, on_saved=self.home.refresh_current))

        self.router.push(onboarding_view(self, finished))

    def show_login(self, message: str | None = None, error: bool = True):
        from screens.auth import login_view
        from screens.ui import set_reporter, toast

        set_reporter(None)
        self.statement_files.clear()
        self.router.reset(login_view(self))
        if message:
            toast(self.page, message, error=error)

    # --- "Sorun bildir" ---
    STATEMENT_FILES_KEPT = 3

    def remember_statement_file(self, statement_id, name: str, content: bytes):
        self.statement_files.pop(statement_id, None)
        self.statement_files[statement_id] = (name, content)
        while len(self.statement_files) > self.STATEMENT_FILES_KEPT:
            self.statement_files.pop(next(iter(self.statement_files)))

    def open_report(self, category: str = "bug", related_statement: str | None = None, error: str | None = None):
        """Opens the report form; technical context is taken from the screen that is open right now."""
        from screens.support import report_context, report_form

        context = report_context(self, error)
        self.router.push(report_form(self, category, related_statement, context))

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
