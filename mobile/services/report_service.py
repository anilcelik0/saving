from .api_client import ApiClient
from .budget_service import _clean

BASE = "saving/reports/"


class ReportService:
    """Read-only reports. month = 'YYYY-MM' (period end, default current); months = period length."""

    def __init__(self, api: ApiClient):
        self.api = api

    async def categories(self, kind="expense", month=None, months=1) -> dict:
        return await self.api.get(BASE + "categories/", params=_clean({"kind": kind, "month": month, "months": months}))

    async def category_transactions(self, category, kind="expense", month=None, months=1) -> list:
        """category: id, or None for uncategorized."""
        return await self.api.get(BASE + "categories/transactions/", params=_clean(
            {"category": category or "none", "kind": kind, "month": month, "months": months}))

    async def trend(self, month=None, months=12) -> dict:
        return await self.api.get(BASE + "trend/", params=_clean({"month": month, "months": months}))

    async def wealth(self, month=None, months=12) -> dict:
        return await self.api.get(BASE + "wealth/", params=_clean({"month": month, "months": months}))
