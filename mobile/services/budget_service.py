from .api_client import ApiClient

BASE = "saving/budget/"


def _clean(params: dict) -> dict:
    return {k: v for k, v in params.items() if v not in (None, "")}


class Resource:
    """Generic REST resource: list/get/create/update/delete."""

    def __init__(self, api: ApiClient, path: str):
        self.api = api
        self.path = BASE + path

    async def list(self, **params):
        return await self.api.get(self.path, params=_clean(params))

    async def get(self, obj_id):
        return await self.api.get(f"{self.path}{obj_id}/")

    async def create(self, data: dict):
        return await self.api.post(self.path, data)

    async def update(self, obj_id, data: dict):
        return await self.api.patch(f"{self.path}{obj_id}/", data)

    async def delete(self, obj_id):
        return await self.api.delete(f"{self.path}{obj_id}/")


class BudgetService:
    def __init__(self, api: ApiClient):
        self.api = api
        self.categories = Resource(api, "categories/")  # not paginated
        self.accounts = Resource(api, "accounts/")  # not paginated
        self.transactions = Resource(api, "transactions/")  # paginated
        self.plans = Resource(api, "plans/")  # paginated; create = recurring or installment entry

    async def upcoming_plans(self, days: int = 30) -> list:
        return await self.api.get(BASE + "plans/upcoming/", params={"days": days})

    async def pay_plan(self, plan_id, amount: str | None = None, date: str | None = None) -> dict:
        return await self.api.post(f"{BASE}plans/{plan_id}/pay/", _clean({"amount": amount, "date": date}))

    async def summary(self, month: str | None = None) -> dict:
        """month: 'YYYY-MM' (default current)."""
        return await self.api.get(BASE + "summary/", params=_clean({"month": month}))
