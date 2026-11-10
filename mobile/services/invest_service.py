from .api_client import ApiClient
from .budget_service import Resource, _clean

BASE = "saving/invest/"


class Deposits(Resource):
    """Time deposits. close/renew only on active ones; reopen undoes a close."""

    async def close(self, obj_id, account=None, amount: str | None = None, date: str | None = None) -> dict:
        return await self.api.post(f"{self.path}{obj_id}/close/", _clean({"account": account, "amount": amount, "date": date}))

    async def reopen(self, obj_id) -> dict:
        return await self.api.post(f"{self.path}{obj_id}/reopen/", {})

    async def renew(self, obj_id, data: dict) -> dict:
        return await self.api.post(f"{self.path}{obj_id}/renew/", _clean(data))


class InvestService:
    def __init__(self, api: ApiClient):
        self.api = api
        self.trades = Resource(api, "trades/", BASE)  # paginated; filters asset=<code>, side
        self.deposits = Deposits(api, "deposits/", BASE)  # paginated; filter status=active,closed,...

    async def assets(self) -> list:
        """Asset catalog with latest price {date, buy, sell} and day change %."""
        return await self.api.get(BASE + "assets/")

    async def history(self, code: str, days: int = 90) -> list:
        return await self.api.get(f"{BASE}assets/{code}/history/", params={"days": days})

    async def portfolio(self) -> dict:
        return await self.api.get(BASE + "portfolio/")
