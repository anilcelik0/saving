import asyncio
import sys

import flet as ft

from config import api_base_url
from screens.theme import apply_theme
from router import Router
from services.api_client import ApiClient
from services.auth_service import AuthService
from services.budget_service import BudgetService
from services.invest_service import InvestService
from services.report_service import ReportService
from services.token_store import TokenStore
from state import AppState


def _ignore_connection_reset(loop):
    """
    Windows (Proactor loop) logs a harmless ConnectionResetError when the peer drops a socket (desktop window
    closed, server closed an idle keep-alive connection). Hide only that; everything else is reported as usual.
    """
    if sys.platform != "win32":
        return

    def handler(loop, context):
        if isinstance(context.get("exception"), ConnectionResetError):
            return
        loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


async def main(page: ft.Page):
    _ignore_connection_reset(asyncio.get_running_loop())
    page.title = "Saving"
    apply_theme(page)

    tokens = TokenStore(ft.SharedPreferences())
    await tokens.load()

    state = AppState(page=page, router=Router(page))
    state.api = ApiClient(api_base_url(page.platform), tokens, on_session_expired=state.on_session_expired)
    state.auth = AuthService(state.api)
    state.budget = BudgetService(state.api)
    state.invest = InvestService(state.api)
    state.reports = ReportService(state.api)

    await state.start()


if __name__ == "__main__":
    ft.run(main)
