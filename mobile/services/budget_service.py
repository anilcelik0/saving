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


class Transactions(Resource):
    """Single money-movement resource. scope: 'this' | 'following' (series occurrences)."""

    async def update(self, obj_id, data: dict, scope: str = "this"):
        return await self.api.patch(f"{self.path}{obj_id}/?scope={scope}", data)

    async def delete(self, obj_id, scope: str = "this"):
        return await self.api.delete(f"{self.path}{obj_id}/?scope={scope}")

    async def upcoming(self, days: int = 30) -> list:
        return await self.api.get(self.path + "upcoming/", params={"days": days})

    async def pay(self, obj_id, amount: str | None = None, date: str | None = None) -> dict:
        return await self.api.post(f"{self.path}{obj_id}/pay/", _clean({"amount": amount, "date": date}))

    async def unpay(self, obj_id) -> dict:
        return await self.api.post(f"{self.path}{obj_id}/unpay/", {})


CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class Statements(Resource):
    """Upload -> poll get() until status 'ready' -> lines() / update_line() -> confirm()."""

    async def upload(self, account_id, filename: str, content: bytes) -> dict:
        ext = filename.rsplit(".", 1)[-1].lower()
        files = {"file": (filename, content, CONTENT_TYPES.get(ext, "application/octet-stream"))}
        return await self.api.upload(self.path, data={"account": account_id}, files=files)

    async def lines(self, statement_id) -> list:
        return await self.api.get(f"{self.path}{statement_id}/lines/")

    async def update_line(self, line_id, data: dict) -> dict:
        return await self.api.patch(f"{BASE}statement-lines/{line_id}/", data)

    async def confirm(self, statement_id) -> dict:
        return await self.api.post(f"{self.path}{statement_id}/confirm/", {})


class BudgetService:
    def __init__(self, api: ApiClient):
        self.api = api
        self.categories = Resource(api, "categories/")  # not paginated
        self.accounts = Resource(api, "accounts/")  # not paginated
        self.transactions = Transactions(api, "transactions/")  # paginated
        self.statements = Statements(api, "statements/")  # paginated

    async def summary(self, month: str | None = None) -> dict:
        """month: 'YYYY-MM' (default current)."""
        return await self.api.get(BASE + "summary/", params=_clean({"month": month}))
